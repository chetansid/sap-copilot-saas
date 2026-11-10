from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os
import shutil
import uuid
import asyncio
from dotenv import load_dotenv
from ingest import delete_project_vectors

load_dotenv(override=False)

from database import get_db, init_db
import models
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, check_subscription
)
from billing import (
    create_stripe_customer, create_checkout_session,
    create_portal_session, handle_webhook
)

app = FastAPI(title="SAP Copilot SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
os.makedirs("uploads", exist_ok=True)


# ── Auth ───────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/signup")
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        models.User.email == request.email
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name
    )
    db.add(user)
    db.flush()

    # Create Stripe customer
    stripe_id = create_stripe_customer(request.email, request.full_name)
    user.stripe_customer_id = stripe_id

    # Create 7-day trial subscription
    trial_end = datetime.utcnow() + timedelta(days=7)
    subscription = models.Subscription(
        user_id=user.id,
        status="trial",
        trial_ends_at=trial_end
    )
    db.add(subscription)
    db.commit()

    token = create_access_token(user.id, user.email)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
        "trial_ends_at": str(trial_end)
    }


@app.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.email == request.email
    ).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, user.email)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name}
    }


@app.get("/auth/me")
def me(current_user: models.User = Depends(get_current_user)):
    sub = current_user.subscription
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "subscription": {
            "status": sub.status if sub else "none",
            "trial_ends_at": str(sub.trial_ends_at) if sub else None,
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "current_period_end": str(sub.current_period_end) if sub and sub.current_period_end else None,
        }
    }


# ── Projects ───────────────────────────────────────────────────────────────────

class ProjectRequest(BaseModel):
    name: str
    client_name: str
    description: str = ""


@app.get("/projects")
def list_projects(
    current_user: models.User = Depends(check_subscription),
    db: Session = Depends(get_db)
):
    projects = db.query(models.Project).filter(
        models.Project.user_id == current_user.id
    ).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "client_name": p.client_name,
            "description": p.description,
            "created_at": str(p.created_at)
        }
        for p in projects
    ]


@app.post("/projects")
def create_project(
    request: ProjectRequest,
    current_user: models.User = Depends(check_subscription),
    db: Session = Depends(get_db)
):
    project = models.Project(
        user_id=current_user.id,
        name=request.name,
        client_name=request.client_name,
        description=request.description
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name, "client_name": project.client_name}


@app.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    current_user: models.User = Depends(check_subscription),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Remove child rows first because project_id is NOT NULL.
        db.query(models.ConversationMessage).filter(
            models.ConversationMessage.project_id == project_id
        ).delete(synchronize_session=False)

        db.query(models.Document).filter(
            models.Document.project_id == project_id
        ).delete(synchronize_session=False)

        # Remove PGVector's collection: u<user_id>_p<project_id>.
        delete_project_vectors(current_user.id, project_id)

        # Bulk delete avoids SQLAlchemy trying to set child project_id values to NULL.
        db.query(models.Project).filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id
        ).delete(synchronize_session=False)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Project deleted"}


# ── Documents ──────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/upload")
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    doc_type: str = "note",
    current_user: models.User = Depends(check_subscription),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    # Save to user-scoped directory
    user_dir = f"uploads/user_{current_user.id}/project_{project_id}"
    os.makedirs(user_dir, exist_ok=True)
    file_path = f"{user_dir}/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Ingest to user-scoped ChromaDB
    from ingest import ingest_file_for_user
    chunks = ingest_file_for_user(
        file_path, doc_type,
        user_id=current_user.id,
        project_id=project_id
    )
    os.remove(file_path)

    # Save metadata to PostgreSQL
    doc = models.Document(
        project_id=project_id,
        user_id=current_user.id,
        filename=file.filename,
        doc_type=doc_type,
        chunks_created=chunks
    )
    db.add(doc)
    db.commit()

    return {"message": f"Ingested {file.filename}", "chunks": chunks}


@app.get("/projects/{project_id}/documents")
def get_documents(
    project_id: int,
    current_user: models.User = Depends(check_subscription),
    db: Session = Depends(get_db)
):
    docs = db.query(models.Document).filter(
        models.Document.project_id == project_id,
        models.Document.user_id == current_user.id
    ).all()
    return [
        {"id": d.id, "filename": d.filename, "doc_type": d.doc_type, "chunks": d.chunks_created}
        for d in docs
    ]


# ── Copilot ────────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    project_id: int


@app.post("/ask-stream")
async def ask_stream(
    request: AskRequest,
    current_user: models.User = Depends(check_subscription),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(
        models.Project.id == request.project_id,
        models.Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    async def generate():
        try:
            # Get conversation history
            messages = db.query(models.ConversationMessage).filter(
                models.ConversationMessage.project_id == request.project_id,
                models.ConversationMessage.user_id == current_user.id
            ).order_by(models.ConversationMessage.created_at.desc()).limit(10).all()

            history = [
                {"role": m.role, "content": m.content}
                for m in reversed(messages)
            ]

            # Add project context
            context_prefix = f"Project: {project.name} | Client: {project.client_name}\n"
            full_question = context_prefix + request.question

            # Run agent with user-scoped retrieval
            from agent import run_agent_for_user
            loop = asyncio.get_event_loop()
            answer = await loop.run_in_executor(
                None,
                lambda: run_agent_for_user(
                    full_question, history,
                    user_id=current_user.id,
                    project_id=request.project_id
                )
            )

            # Save to PostgreSQL
            user_msg = models.ConversationMessage(
                project_id=request.project_id,
                user_id=current_user.id,
                role="user",
                content=request.question
            )
            ai_msg = models.ConversationMessage(
                project_id=request.project_id,
                user_id=current_user.id,
                role="assistant",
                content=answer
            )
            db.add(user_msg)
            db.add(ai_msg)
            db.commit()

            # Stream word by word
            for word in answer.split(' '):
                yield f"data: {word} \n\n"
                await asyncio.sleep(0.02)

            yield "data: [DONE]\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: Error: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ── Billing ────────────────────────────────────────────────────────────────────

@app.get("/billing/checkout")
def checkout(current_user: models.User = Depends(get_current_user)):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer")
    url = create_checkout_session(current_user.stripe_customer_id, current_user.id)
    return {"url": url}


@app.get("/billing/portal")
def portal(current_user: models.User = Depends(get_current_user)):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer")
    url = create_portal_session(current_user.stripe_customer_id)
    return {"url": url}


@app.post("/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = handle_webhook(payload, sig_header)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = int(session["metadata"]["user_id"])
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user and user.subscription:
            user.subscription.status = "active"
            # user.subscription.stripe_subscription_id = session.get("subscription")
            user.subscription.stripe_subscription_id = session.subscription
            db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"]["id"]
        sub = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == sub_id
        ).first()
        if sub:
            sub.status = "cancelled"
            db.commit()

    elif event["type"] == "customer.subscription.updated":
        obj = event["data"]["object"].to_dict()
        sub = db.query(models.Subscription).filter(
            models.Subscription.stripe_subscription_id == obj["id"]
        ).first()
        if sub:
            sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end") or obj.get("cancel_at"))
            # Newer Stripe API versions move this field onto the subscription item
            ts = obj.get("current_period_end") or \
                 (obj.get("items", {}).get("data") or [{}])[0].get("current_period_end")
            if ts:
                sub.current_period_end = datetime.utcfromtimestamp(ts)
            if obj.get("status") in ("past_due", "unpaid"):
                sub.status = "past_due"
            elif obj.get("status") == "active":
                sub.status = "active"
            db.commit()

    return {"status": "ok"}

@app.get("/projects/{project_id}/messages")
def get_messages(project_id: int, current_user: models.User = Depends(check_subscription), db: Session = Depends(get_db)):
    msgs = db.query(models.ConversationMessage).filter(
        models.ConversationMessage.project_id == project_id,
        models.ConversationMessage.user_id == current_user.id
    ).order_by(models.ConversationMessage.created_at).limit(100).all()
    return [{"role": m.role, "content": m.content} for m in msgs]
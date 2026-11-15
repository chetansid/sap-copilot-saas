from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
# from ingest import get_vectorstore
from dotenv import load_dotenv
from contextvars import ContextVar

import os

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Multi-tenancy context — set by agent before each request
CURRENT_USER_ID = ContextVar("user_id", default=None)
CURRENT_PROJECT_ID = ContextVar("project_id", default=None)


def get_user_vectorstore():
    from ingest import get_vectorstore_for_user
    uid, pid = CURRENT_USER_ID.get(), CURRENT_PROJECT_ID.get()
    if uid is None or pid is None:
        raise RuntimeError("No tenant context set")  # fail closed, never fall back to shared data
    return get_vectorstore_for_user(uid, pid)


def search_documents(query: str, doc_type: str = None) -> str:
    vectorstore = get_user_vectorstore()  # now user-scoped
    if doc_type:
        results = vectorstore.similarity_search(query, k=6, filter={"doc_type": doc_type})
    else:
        results = vectorstore.similarity_search(query, k=6)

    if not results:
        return "No relevant documents found."

    return "\n\n".join([
        f"[Source: {doc.metadata.get('source_file')} — Page {doc.metadata.get('page', 0) + 1}]\n{doc.page_content}"
        for doc in results
    ])

def generate_technical_design(spec_content: str, template_content: str = None) -> str:
    template_instruction = ""
    if template_content:
        template_instruction = f"""
        IMPORTANT: Follow this exact structure and format from the provided template:
        {template_content[:2000]}
        Mirror the naming conventions, section headings, and level of detail exactly.
        """

    prompt = ChatPromptTemplate.from_template("""
    You are a senior SAP technical architect at EY working on Fortune 500 S/4HANA implementations.
    
    {template_instruction}
    
    Based on the functional specification below, generate a detailed technical design document.

    Structure your response exactly as follows:

    ## 1. Solution Overview
    Brief technical approach and chosen implementation method.

    ## 2. Object Details
    - Object Type: (Report/Interface/Conversion/Enhancement/Form/Workflow)
    - Development Class/Package:
    - Transaction Code (if applicable):
    - Program Name:

    ## 3. Data Mapping
    | Source Field | Source Table | Target Field | Target Table | Transformation Logic |
    |---|---|---|---|---|
    (List all field mappings)

    ## 4. Function Modules / BAPIs
    List each FM/BAPI with purpose and key parameters.

    ## 5. ABAP Pseudocode
    REPORT z_<object_name>.
* Main logic pseudocode

    ## 6. Error Handling
    - Error scenarios and handling approach
    - Message classes to use

    ## 7. Transport Strategy
    - Development system: DEV
    - Quality system: QAS  
    - Production system: PRD
    - Transport request naming convention

    ## 8. Testing Checklist
    - [ ] Unit testing in DEV
    - [ ] Integration testing in QAS
    - [ ] UAT sign-off required
    - [ ] Performance testing (if applicable)

    ## 9. Open Items / Assumptions
    List any assumptions made or items needing clarification.

    Functional Specification:
    {spec}
    """)

    chain = prompt | llm | StrOutputParser()
    return chain.invoke({
        "spec": spec_content,
        "template_instruction": template_instruction
    })


def generate_basis_script(requirement: str) -> str:
    prompt = ChatPromptTemplate.from_template("""
    You are an expert SAP BASIS administrator with 15 years of experience on Fortune 500 landscapes.
    Generate a complete, executable procedure for the following requirement.

    Structure your response as follows:

    ## Overview
    What this script/procedure does and when to use it.

    ## Prerequisites
    - Required authorizations (t-codes and authorization objects)
    - System state requirements
    - Backup recommendations if applicable

    ## Step-by-Step Procedure

    ### Via Transaction Code:
    1. Go to [T-CODE] → [exact menu path]
    2. [Exact field values to enter]
    3. [What to look for in output]

    ### Via ABAP (if applicable):
```abap
    *& Report name
    REPORT z_basis_<name>.

    * Actual executable ABAP code here
    * Include table names, field names, and logic
```

    ## Expected Output
    Describe exactly what a successful result looks like.

    ## Verification Steps
    How to confirm the action completed successfully.

    ## Rollback Procedure
    How to undo this action if needed.

    ## Common Issues
    - Issue 1: [symptom] → [fix]
    - Issue 2: [symptom] → [fix]

    Requirement: {requirement}
    """)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"requirement": requirement})


def analyze_sap_log(log_content: str) -> str:
    prompt = ChatPromptTemplate.from_template("""
    You are an expert SAP BASIS administrator analyzing system logs for a Fortune 500 client.

    Structure your analysis as follows:

    ## Log Summary
    One paragraph describing what this log shows overall.

    ## Critical Issues Found
    | Severity | Issue | Transaction/Program | Root Cause |
    |---|---|---|---|
    (List all issues found — HIGH/MEDIUM/LOW severity)

    ## Root Cause Analysis
    For each critical issue, explain:
    - What exactly happened
    - Why it happened
    - What triggered it

    ## Performance Observations
    - Response times, memory usage, work process utilization if visible
    - Bottlenecks identified

    ## Immediate Actions Required
    Numbered list of actions to take RIGHT NOW, with exact t-codes.

    ## Medium-Term Recommendations
    Actions to take within the next week to prevent recurrence.

    ## Monitoring Recommendations
    - Which t-codes to monitor regularly
    - Thresholds to set up alerts for

    SAP Log:
    {log}
    """)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"log": log_content})


def summarize_notes(query: str) -> str:
    context = search_documents(query, doc_type="note")

    if context == "No relevant documents found.":
        return "No implementation notes found. Please upload notes first."

    prompt = ChatPromptTemplate.from_template("""
    You are a senior SAP implementation consultant at EY summarizing project notes.

    Query: {query}

    Structure your summary as follows:

    ## Key Decisions Made
    - Decision 1: [what was decided and why]
    - Decision 2: ...

    ## Open Items
    | # | Item | Owner | Due Date | Priority |
    |---|---|---|---|---|
    (Extract all open/pending items)

    ## Risks and Issues
    | Risk/Issue | Impact | Mitigation |
    |---|---|---|

    ## Dependencies
    List any dependencies between workstreams or systems.

    ## Next Steps
    Prioritized list of next actions.

    ## Questions Needing Answers
    List any unresolved questions from the notes.

    Notes:
    {context}
    """)
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"query": query, "context": context})
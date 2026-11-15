from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from typing import TypedDict, List, Literal, Optional
from dotenv import load_dotenv
import json

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── State ──────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    question: str
    messages: List
    tool_calls_made: List[str]
    tool_results: List[str]
    sufficient: bool
    answer: str
    iterations: int
    next_tool: Optional[str]
    tool_argument: Optional[str]


# ── Tools ──────────────────────────────────────────────────────────────────────

TOOLS = {}

def get_tools():
    global TOOLS
    if not TOOLS:
        from tools import (
            search_documents,
            generate_technical_design,
            generate_basis_script,
            analyze_sap_log,
            summarize_notes
        )
        TOOLS = {
            "search_ricefw": lambda q: search_documents(q, doc_type="ricefw"),
            "search_notes": lambda q: search_documents(q, doc_type="note"),
            "search_all": lambda q: search_documents(q),
            "generate_technical_design": generate_technical_design,
            "generate_basis_script": generate_basis_script,
            "analyze_log": analyze_sap_log,
            "summarize_notes": summarize_notes,
        }
    return TOOLS


TOOL_DESCRIPTIONS = """
Available tools:
- search_ricefw(query): Search uploaded RICEFW functional specifications
- search_notes(query): Search uploaded implementation notes and meeting minutes
- search_all(query): Search across ALL uploaded documents
- generate_technical_design(spec_content): Generate technical design from spec content
- generate_basis_script(requirement): Generate BASIS admin script or procedure
- analyze_log(log_content): Analyze SAP system log for issues
- summarize_notes(query): Summarize notes and extract open items
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

def decide_next_tool(state: AgentState) -> AgentState:
    question = state["question"]
    tool_calls_made = state["tool_calls_made"]
    tool_results = state["tool_results"]
    iterations = state["iterations"]

    

    if iterations >= 4:
        
        new_state = dict(state)
        new_state["sufficient"] = True
        new_state["iterations"] = iterations + 1
        return new_state

    history_context = ""
    if tool_calls_made:
        history_context = "\n\nTools already called:\n"
        for i, (call, result) in enumerate(zip(tool_calls_made, tool_results)):
            history_context += f"Tool {i+1}: {call} → Result preview: {result[:300]}\n"

    prompt = f"""You are an expert SAP implementation copilot.

Question: {question}
{history_context}

{TOOL_DESCRIPTIONS}

Tools already called (DO NOT repeat ANY of these): {tool_calls_made}
Number of results collected so far: {len(tool_results)}
RULE: If len(tool_results) >= 2, set sufficient=true immediately.

STRICT RULES:
- Never call a tool that appears in "Tools already called" list above
- For conflict detection: call search_ricefw FIRST, then search_notes SECOND
- If search_ricefw is in already-called list → next tool MUST be search_notes
- If both search_ricefw AND search_notes are in already-called list → sufficient=true
- Questions about uploaded documents → always call search tools before answering
- BASIS scripts → call generate_basis_script directly, then sufficient=true
- Log analysis → call analyze_log directly, then sufficient=true
- After any 2 tool calls → set sufficient=true

Respond with ONLY this JSON, no other text:
{{
    "sufficient": false,
    "reasoning": "why you need more info",
    "next_tool": "tool_name",
    "tool_argument": "what to search for"
}}

OR if you have enough information:
{{
    "sufficient": true,
    "reasoning": "why you have enough",
    "next_tool": null,
    "tool_argument": null
}}"""

    response = llm.invoke([HumanMessage(content=prompt)])

    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        decision = json.loads(content.strip())
    except Exception as e:
        decision = {"sufficient": True, "reasoning": "parse error", "next_tool": None, "tool_argument": None}



    new_state = dict(state)
    new_state["sufficient"] = decision.get("sufficient", True)
    new_state["next_tool"] = decision.get("next_tool")
    new_state["tool_argument"] = decision.get("tool_argument")
    new_state["iterations"] = iterations + 1

    if not decision.get("sufficient") and decision.get("next_tool"):
        new_state["tool_calls_made"] = tool_calls_made + [decision["next_tool"]]

    return new_state


def call_tool(state: AgentState) -> AgentState:
    next_tool = state.get("next_tool")
    tool_argument = state.get("tool_argument") or state["question"]
    tool_results = state["tool_results"]


    tools = get_tools()

    if not next_tool or next_tool not in tools:
        
        new_state = dict(state)
        new_state["tool_results"] = tool_results + [f"Tool {next_tool} not found"]
        return new_state

    try:
        result = tools[next_tool](tool_argument)
        
    except Exception as e:
        result = f"Tool error: {str(e)}"
        

    new_state = dict(state)
    new_state["tool_results"] = tool_results + [result]
    return new_state


def formulate_answer(state: AgentState) -> AgentState:
    question = state["question"]
    tool_calls_made = state["tool_calls_made"]
    tool_results = state["tool_results"]
    messages = state.get("messages", [])

    

    if tool_results:
        context = "\n\n".join([
            f"[From {tool}]:\n{result}"
            for tool, result in zip(tool_calls_made, tool_results)
        ])
    else:
        context = "No documents found — answering from general SAP knowledge."

    system = """You are an expert SAP implementation copilot for EY consultants.
Be precise, practical, and reference specific SAP transaction codes.
When analyzing conflicts, cite specific sections or fields from the documents.
Format responses clearly."""

    prompt_messages = [SystemMessage(content=system)]
    if messages:
        prompt_messages.extend(messages[-4:])

    if context and "No documents" not in context:
        prompt_messages.append(HumanMessage(
            content=f"Document content retrieved:\n{context}\n\nQuestion: {question}\n\nAnalyze the actual document content above to answer this question."
        ))
    else:
        prompt_messages.append(HumanMessage(content=question))

    response = llm.invoke(prompt_messages)

    new_state = dict(state)
    new_state["answer"] = response.content
    return new_state


def should_continue(state: AgentState) -> Literal["call_tool", "formulate_answer"]:
    sufficient = state.get("sufficient", False)
    next_tool = state.get("next_tool")
    if sufficient or not next_tool:
        return "formulate_answer"
    return "call_tool"


# ── Build Graph ────────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("decide_next_tool", decide_next_tool)
    graph.add_node("call_tool", call_tool)
    graph.add_node("formulate_answer", formulate_answer)
    graph.set_entry_point("decide_next_tool")
    graph.add_conditional_edges(
        "decide_next_tool",
        should_continue,
        {
            "call_tool": "call_tool",
            "formulate_answer": "formulate_answer"
        }
    )
    graph.add_edge("call_tool", "decide_next_tool")
    graph.add_edge("formulate_answer", END)
    return graph.compile()


agent = build_graph()


def run_agent(question: str, history: list = []) -> str:
    state = AgentState(
        question=question,
        messages=history,
        tool_calls_made=[],
        tool_results=[],
        sufficient=False,
        answer="",
        iterations=0,
        next_tool=None,
        tool_argument=None
    )
    result = agent.invoke(state)
    return result["answer"]

def run_agent_for_user(question, history, user_id, project_id):
    import tools
    t1 = tools.CURRENT_USER_ID.set(user_id)
    t2 = tools.CURRENT_PROJECT_ID.set(project_id)
    try:
        return run_agent(question, history)
    finally:
        tools.CURRENT_USER_ID.reset(t1)
        tools.CURRENT_PROJECT_ID.reset(t2)
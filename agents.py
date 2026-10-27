import json
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from schemas import JDEvaluation, TailoredResumeContent, FormAnswer, JobApplicationState
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq LLM using high-performance Llama 3.3 70B
llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.1)

def evaluate_jd_node(state: JobApplicationState) -> dict:
    """Node 1: Evaluates the JD against the Master Profile using json_mode with exact schema keys."""
    structured_llm = llm.with_structured_output(JDEvaluation, method="json_mode")
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a technical recruiter and job triage agent. Analyze the Job Description against the "
            "Candidate Master Profile.\n"
            "You MUST return a JSON object with EXACTLY the following keys:\n"
            "- \"role_archetype\": Must be one of 'Data Analyst', 'Data Scientist', or 'AI/ML Engineer'\n"
            "- \"min_years_experience\": Integer representing minimum years required (e.g., 3)\n"
            "- \"fit_score\": Integer from 0 to 100 representing candidate match\n"
            "- \"required_skills\": Array of strings listing required technical skills\n"
            "- \"reasoning\": String explaining the fit score breakdown\n\n"
            "CRITICAL: Respond strictly in valid JSON format matching these exact keys."
        )),
        ("human", "Job Title: {title}\nCompany: {company}\n\nJob Description:\n{jd_text}\n\nCandidate Profile:\n{profile}")
    ])
    chain = prompt | structured_llm
    evaluation = chain.invoke({
        "title": state["title"],
        "company": state["company"],
        "jd_text": state["jd_text"],
        "profile": json.dumps(state["master_profile"], indent=2)
    })
    print(f"[Evaluator - Groq] {state['title']} @ {state['company']} -> Archetype: {evaluation.role_archetype} | Fit: {evaluation.fit_score}%")
    return {"evaluation": evaluation}

def tailor_resume_node(state: JobApplicationState) -> dict:
    """Node 2: Optimizes resume to target 96% ATS keyword coverage using json_mode with exact schema keys."""
    structured_llm = llm.with_structured_output(TailoredResumeContent, method="json_mode")
    eval_data: JDEvaluation = state["evaluation"]
    attempts = state.get("rewrite_attempts", 0) + 1

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an expert ATS Resume Optimization Agent. Your goal is to rewrite and restructure "
            "the candidate's Master Profile to achieve a **96% or higher ATS keyword coverage** against the target Job Description.\n\n"
            "MANDATORY GUIDELINES:\n"
            "1. **STRICT PROJECT LOCK:** You MUST retain the exact project names from the Master Profile (e.g., 'Item Analysis Automation Platform', 'AI Ticket Logger & Productivity Automation', 'Student Lifetime Value & Journey Analysis'). Do NOT invent new project names or change canonical project titles.\n"
            "2. **Zero Hallucination:** Never invent employers, degrees, or unverified skills.\n"
            "3. **Targeted Keyword Customization:** Tailor the experience bullets and project bullets to weave in required skills: {required_skills}.\n"
            "CRITICAL: Return valid JSON matching the exact schema keys (`headline`, `summary`, `skill_categories`, `experience`, `selected_projects`, `ats_keyword_coverage_pct`)."
        )),
        ("human", "Target JD:\n{jd_text}\n\nCandidate Master Profile:\n{profile}")
    ])
    chain = prompt | structured_llm
    tailored = chain.invoke({
        "archetype": eval_data.role_archetype,
        "required_skills": ", ".join(eval_data.required_skills),
        "jd_text": state["jd_text"],
        "profile": json.dumps(state["master_profile"], indent=2)
    })
    print(f"[Tailor Agent - Groq] Draft #{attempts} complete. Estimated ATS keyword coverage: {tailored.ats_keyword_coverage_pct}%")
    return {"tailored_resume": tailored, "rewrite_attempts": attempts}

def answer_screening_question(question_text: str, options: list[str], master_profile: dict) -> str:
    """Helper agent called by Playwright during modal filling using json_mode."""
    structured_llm = llm.with_structured_output(FormAnswer, method="json_mode")
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are filling out a LinkedIn Easy Apply screening question on behalf of the candidate.\n"
            "If options are provided, you MUST return the exact string of one of the options.\n"
            "If it asks for numeric years of experience or CTC, return ONLY the number (e.g., '3' or '12').\n"
            "Use the candidate's screening_facts below.\n"
            "CRITICAL: You must respond strictly in valid JSON format matching the requested schema."
        )),
        ("human", "Question: {question}\nOptions (if any): {options}\nCandidate Facts: {facts}")
    ])
    chain = prompt | structured_llm
    res = chain.invoke({
        "question": question_text,
        "options": options if options else "Free text / Numeric input",
        "facts": json.dumps(master_profile.get("screening_facts", {}))
    })
    return res.answer
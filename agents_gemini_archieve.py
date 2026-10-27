import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from schemas import JDEvaluation, TailoredResumeContent, FormAnswer, JobApplicationState
from dotenv import load_dotenv

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0.1)

def evaluate_jd_node(state: JobApplicationState) -> dict:
    """Node 1: Evaluates the JD against the Master Profile and assigns a fit score & archetype."""
    structured_llm = llm.with_structured_output(JDEvaluation)
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a technical recruiter and job triage agent. Analyze the Job Description against the "
            "Candidate Master Profile. Classify the role into 'Data Analyst', 'Data Scientist', or 'AI/ML Engineer', "
            "extract required skills, and compute a realistic fit_score (0-100)."
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
    print(f"[Evaluator] {state['title']} @ {state['company']} -> Archetype: {evaluation.role_archetype} | Fit: {evaluation.fit_score}%")
    return {"evaluation": evaluation}

def tailor_resume_node(state: JobApplicationState) -> dict:
    """Node 2: Re-weights bullets and weaves ATS keywords without fabricating unverified skills."""
    structured_llm = llm.with_structured_output(TailoredResumeContent)
    eval_data: JDEvaluation = state["evaluation"]
    attempts = state.get("rewrite_attempts", 0) + 1

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an expert ATS Resume Tailoring Agent. Rewrite and reorder the candidate's Master Profile "
            "to maximize alignment with the target Job Description for the '{archetype}' track.\n"
            "STRICT GUARDRAILS:\n"
            "1. NEVER invent companies, degrees, or unverified tools not present in the Master Profile.\n"
            "2. Rephrase existing experience and project bullets to naturally incorporate these target JD skills "
            "where truthful: {required_skills}.\n"
            "3. Keep bullets concise, metric-driven, and strictly formatted for a 1-page resume."
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
    print(f"[Tailor Agent] Draft #{attempts} complete. Estimated ATS keyword coverage: {tailored.ats_keyword_coverage_pct}%")
    return {"tailored_resume": tailored, "rewrite_attempts": attempts}

def answer_screening_question(question_text: str, options: list[str], master_profile: dict) -> str:
    """Helper agent called by Playwright during modal filling to answer custom screening questions."""
    structured_llm = llm.with_structured_output(FormAnswer)
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are filling out a LinkedIn Easy Apply screening question on behalf of the candidate.\n"
            "If options are provided, you MUST return the exact string of one of the options.\n"
            "If it asks for numeric years of experience or CTC, return ONLY the number (e.g., '3' or '12').\n"
            "Use the candidate's screening_facts below."
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
from typing import List, Literal, Optional, TypedDict, Any
from pydantic import BaseModel, Field, model_validator, AliasChoices

class JDEvaluation(BaseModel):
    role_archetype: Literal["Data Analyst", "Data Scientist", "AI/ML Engineer"] = Field(
        description="Classify the job into one of the three target tracks."
    )
    required_skills: List[str] = Field(
        description="Key technical skills, tools, and frameworks explicitly mentioned in the JD."
    )
    min_years_experience: float = Field(
        description="Minimum years of experience requested in the JD (0 if not stated)."
    )
    fit_score: int = Field(
        description="Score from 0 to 100 indicating how well the candidate's master profile matches the JD.",
        ge=0, le=100
    )
    reasoning: str = Field(description="Brief explanation for the assigned fit score.")

class SkillCategory(BaseModel):
    name: str = Field(
        validation_alias=AliasChoices('name', 'category'),
        description="Category name e.g., 'DATA & BI', 'ANALYTICS'"
    )
    skills: List[str] = Field(description="List of skills under this category")

class ExperienceItem(BaseModel):
    company: str
    role: str
    duration: str
    bullets: List[str] = Field(description="3 to 4 tailored, high-impact ATS bullet points.")

class ProjectItem(BaseModel):
    name: str
    bullets: List[str] = Field(description="2 tailored bullet points highlighting relevant stack.")

class TailoredResumeContent(BaseModel):
    headline: str = Field(description="Target role title aligned with the JD.")
    summary: str = Field(description="3-sentence executive summary tailored to the JD keywords.")
    skill_categories: List[SkillCategory] = Field(description="Grouped technical skill categories.")
    experience: List[ExperienceItem]
    selected_projects: List[ProjectItem] = Field(description="Top 2 most relevant projects.")
    ats_keyword_coverage_pct: int = Field(description="Estimated integer percentage of JD required_skills covered (e.g. 96).")

    @model_validator(mode='before')
    @classmethod
    def coerce_types(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Round float percentages to integers
            cov = data.get("ats_keyword_coverage_pct")
            if isinstance(cov, float):
                data["ats_keyword_coverage_pct"] = int(round(cov))
            
            # 2. Automatically convert dict skill_categories to list of objects if LLM formats it as a dict
            sc = data.get("skill_categories")
            if isinstance(sc, dict):
                data["skill_categories"] = [
                    {"name": k, "skills": v} for k, v in sc.items()
                ]
        return data

class FormAnswer(BaseModel):
    answer: str = Field(description="Concise, direct value to fill into the form input.")

# LangGraph Shared State
class JobApplicationState(TypedDict):
    job_id: str
    title: str
    company: str
    job_url: str
    jd_text: str
    master_profile: dict
    evaluation: Optional[JDEvaluation]
    tailored_resume: Optional[TailoredResumeContent]
    pdf_path: Optional[str]
    rewrite_attempts: int
    application_status: str
    error_message: Optional[str]
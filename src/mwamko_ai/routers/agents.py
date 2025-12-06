from typing import Annotated, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import openai
from datetime import datetime, timedelta
import asyncio
import json

from mwamko_ai.database import get_db
from mwamko_ai.routers.auth import get_current_user
from mwamko_ai.models import EmergencyCases, Routes, Users
from mwamko_ai.config import settings


router = APIRouter(
    prefix="/ai",
    tags=["AI Agents"]
)

class AIConfig:
    """AI Configuration settings"""
    OPENAI_API_KEY = settings.OPENAI_API_KEY
    GPT_MODEL = "gpt-4o-mini" # or "gpt-3.5-turbo" for cost efficiency
    EMBEDDING_MODEL = "text-embedding-3-small"

class AIRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = None

class AIResponse(BaseModel):
    response: str
    reasoning: str
    actions_taken: List[str] = []
    confidence: float

# Initialize AI clients
openai.api_key = AIConfig.OPENAI_API_KEY


# Agent System
class EmergencyResponseAgent:
    """Main AI agent for emergency response coordination"""
    def __init__(self):
        self.system_prompt = """
        You are Mwamko AI Emergency Response Coordinator. You help coordinate disaster response in Taita Taveta County, Kenya.

        CAPABILITIES:
        1. Analyze emergency cases and prioritize based on severity
        2. Suggest optimal resource allocation
        3. Generate situational reports
        4. Provide decision support for route planning
        5. Monitor response progress and suggest adjustments

        RESPONSE GUIDELINES:
        Always consider geographical constraints and road conditions
        Prioritize human life and critical infrastructure
        Consider available resources and response teams
        Provide clear, actionable recommendations
        Reference real-time data when available
    """
        
    async def analyze_emergency_situation(self, cases: List[EmergencyCases]) -> Dict[str, Any]:
        """Analyze multiple emergency cases and provide coordinated response plan"""
        cases_context = "\n".join([
            f"Case {case.case_id}: {case.disaster_type} in {case.village}, "
            f"Severity: {case.severity}, Status: {case.status}"
            for case in cases
        ])

        prompt = f"""
        EMERGENCY SITUATION ANALYSIS REQUESTED:
        Current Active Cases:
        {cases_context}

        Please analyze this situation and provide:
        1. Priority ranking of cases
        2. Recommended resource allocation
        3. Potential risks and mitigation strategies
        4. Coordination recommendations

        Consider:
        - Severity levels
        - Geographical distribution
        - Available response teams
        - Road accessibility
        - Weather conditions (if available)
        """

        response = await self._call_llm(prompt)
        return self._parse_analysis_response(response)
    
    async def generate_route_recommendations(self, route: Routes, cases: List[EmergencyCases]) -> Dict[str, Any]:
        """AI-powered route optimization and recommendations"""
        prompt = f"""
        ROUTE OPTIMIZATION ANALYSIS:
        Current Route:
        - Total Cost: {route.total_cost}
        - Segments: {len(route.route_segments)}
        - Sequence: {route.optimized_sequence}

        Cases to Serve:
        {[f'Case {case.case_id}: {case.disaster_type} in {case.village}' for case in cases]}

        Provide recommendations for:
        1. Route efficiency improvements
        2. Potential hazards or obstacles
        3. Alternative routes if needed
        4. Estimated response times
        5. Resource allocation along the route
        """

        response = await self._call_llm(prompt)
        return self._parse_route_recommendations(response)
    
    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt"""
        try:
            response = openai.chat.completions.create(
                model=AIConfig.GPT_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for more consistent responses
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI Service temporarily unavailable: {str(e)}"
        
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse AI response into structured data"""
        # Simple parsing - you can implement more sophisticated parsing
        return {
            "analysis": response,
            "timestamp": datetime.now().isoformat(),
            "recommendations": self._extract_recommendations(response)
        }
    
    def _parse_route_recommendations(self, response: str) -> Dict[str, Any]:
        return {
            "route_analysis": response,
            "timestamp": datetime.now().isoformat()
        }
    
    def _extract_recommendations(self, text: str) -> List[str]:
        """Extract actionable recommendations from AI response"""
        # Implement recommendation extraction logic
        lines = text.split('\n')
        recommendations = [line.strip('- ').strip() for line in lines if line.strip().startswith('-')]
        return recommendations if recommendations else ["Review the analysis for specific recommendations"]
    
    def _aggregate_disaster_types(self, cases: List[EmergencyCases]) -> str:
        """Aggregate disaster types for analysis - now uses standalone function"""
        return aggregate_disaster_types(cases)
    
    def _analyze_seasonal_patterns(self, cases: List[EmergencyCases]) -> str:
        """Analyze seasonal patterns in emergencies - now uses standalone function"""
        return analyze_seasonal_patterns(cases)
    

# Initialize agents
emergency_agent = EmergencyResponseAgent()

@router.post("/analyze-emergencies", response_model=AIResponse)
async def analyze_emergencies(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """AI analysis of all active emergencies"""
    # Get active emergency cases
    active_cases = db.query(EmergencyCases).filter(
        EmergencyCases.status.in_(['PENDING', 'IN PROGRESS'])
    ).all()
    
    if not active_cases:
        raise HTTPException(status_code=404, detail="No active emergencies found")
    
    # Run AI analysis
    analysis = await emergency_agent.analyze_emergency_situation(active_cases)
    
    # Store analysis in database (optional)
    background_tasks.add_task(store_ai_analysis, analysis, current_user['id'])
    
    return AIResponse(
        response=analysis["analysis"],
        reasoning="Analyzed current emergency situation and provided coordinated response plan",
        actions_taken=["Situation analysis", "Priority assessment", "Resource allocation planning"],
        confidence=0.85
    )

@router.post("/optimize-route/{route_id}", response_model=AIResponse)
async def ai_optimize_route(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """AI-powered route optimization and recommendations"""
    route = db.query(Routes).filter(Routes.route_id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    
    # Get cases associated with this route
    case_ids = await get_case_ids_from_route(db, route.optimized_sequence)
    cases = db.query(EmergencyCases).filter(EmergencyCases.case_id.in_(case_ids)).all()
    
    recommendations = await emergency_agent.generate_route_recommendations(route, cases)
    
    return AIResponse(
        response=recommendations["route_analysis"],
        reasoning="Analyzed route efficiency and provided optimization suggestions",
        actions_taken=["Route analysis", "Hazard assessment", "Alternative route evaluation"],
        confidence=0.80
    )

@router.post("/predictive-alerts")
async def generate_predictive_alerts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Generate predictive alerts based on historical data and current conditions"""
    
    # Get historical emergency data
    historical_cases = db.query(EmergencyCases).filter(
        EmergencyCases.created_at >= datetime.now() - timedelta(days=365)
    ).all()
    
    if not historical_cases:
        raise HTTPException(status_code=404, detail="No historical data available")
    
    # Aggregate data for analysis
    disaster_types = aggregate_disaster_types(historical_cases)
    seasonal_patterns = analyze_seasonal_patterns(historical_cases)
    
    prompt = f"""
    PREDICTIVE ANALYSIS REQUEST:
    
    Historical Emergency Data (Past Year):
    {len(historical_cases)} total cases
    
    Common Disaster Types:
    {disaster_types}
    
    Seasonal Patterns:
    {seasonal_patterns}
    
    Provide predictive insights:
    1. High-risk areas and time periods
    2. Recommended preventive measures
    3. Resource pre-positioning suggestions
    4. Early warning indicators to monitor
    """
    
    response = await emergency_agent._call_llm(prompt)
    
    return {
        "predictive_insights": response,
        "generated_at": datetime.now().isoformat(),
        "data_points_analyzed": len(historical_cases)
    }

# Move helper functions outside the class to make them accessible
def aggregate_disaster_types(cases: List[EmergencyCases]) -> str:
    """Aggregate disaster types for analysis"""
    from collections import Counter
    disaster_counts = Counter([case.disaster_type for case in cases])
    return "\n".join([f"{disaster}: {count} cases" for disaster, count in disaster_counts.items()])

def analyze_seasonal_patterns(cases: List[EmergencyCases]) -> str:
    """Analyze seasonal patterns in emergencies"""
    monthly_counts = {}
    for case in cases:
        month = case.created_at.month
        monthly_counts[month] = monthly_counts.get(month, 0) + 1
    
    # Convert month numbers to names for better readability
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    
    monthly_named = {month_names.get(month, month): count for month, count in monthly_counts.items()}
    return f"Monthly distribution: {monthly_named}"

# Helper functions
async def store_ai_analysis(analysis: Dict[str, Any], user_id: int):
    """Store AI analysis in database"""
    # Implement storage logic
    pass

async def get_case_ids_from_route(db: Session, optimized_sequence: List[int]) -> List[int]:
    """Get case IDs from route nodes"""
    # Implementation from previous code
    return []  # Placeholder
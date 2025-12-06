from typing import Dict, List, Any
from sqlalchemy.orm import Session
from mwamko_ai.models import EmergencyCases, Users

class ResourceAllocationAgent:
    """AI agent for optimal resource allocation"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def optimize_resource_allocation(self, emergencies: List[EmergencyCases]) -> Dict[str, Any]:
        """Optimize resource allocation across multiple emergencies"""
        
        # Get available resources
        available_teams = self.db.query(Users).filter(
            Users.role == 'Rescue Team',
            Users.is_active == True
        ).all()
        
        allocation_plan = {
            'teams_assigned': {},
            'priority_ranking': [],
            'estimated_completion_times': {},
            'resource_gaps': []
        }
        
        # Sort emergencies by severity and other factors
        prioritized_emergencies = self._prioritize_emergencies(emergencies)
        
        # Allocate teams
        for emergency in prioritized_emergencies:
            suitable_team = self._find_best_team(emergency, available_teams)
            if suitable_team:
                allocation_plan['teams_assigned'][emergency.case_id] = suitable_team.id
                available_teams.remove(suitable_team)
            else:
                allocation_plan['resource_gaps'].append(emergency.case_id)
        
        return allocation_plan
    
    def _prioritize_emergencies(self, emergencies: List[EmergencyCases]) -> List[EmergencyCases]:
        """Prioritize emergencies using multi-factor analysis"""
        scored_emergencies = []
        
        for emergency in emergencies:
            score = self._calculate_priority_score(emergency)
            scored_emergencies.append((score, emergency))
        
        # Sort by score (descending)
        scored_emergencies.sort(key=lambda x: x[0], reverse=True)
        return [emergency for score, emergency in scored_emergencies]
    
    def _calculate_priority_score(self, emergency: EmergencyCases) -> float:
        """Calculate priority score based on multiple factors"""
        severity_weights = {
            'Critical': 10,
            'High': 7,
            'Medium': 4,
            'Low': 1
        }
        
        disaster_weights = {
            'Floods': 9,
            'Fire': 10,
            'Landslide': 8,
            'Wildlife Conflict': 6,
            'Drought': 3
        }
        
        base_score = severity_weights.get(emergency.severity, 5)
        disaster_multiplier = disaster_weights.get(emergency.disaster_type, 1)
        
        # Consider time factor (older emergencies get higher priority)
        time_factor = min((datetime.now() - emergency.created_at).total_seconds() / 3600, 24) / 24
        
        return base_score * disaster_multiplier * (1 + time_factor)
    
    def _find_best_team(self, emergency: EmergencyCases, available_teams: List[Users]) -> Users:
        """Find the best available team for the emergency"""
        if not available_teams:
            return None
        
        # Simple implementation - return first available team
        # Enhanced version would consider team specialization, location, etc.
        return available_teams[0] if available_teams else None
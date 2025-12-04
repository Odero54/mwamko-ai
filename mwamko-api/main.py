from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import engine, get_db
from models import Base
from routers import auth, admin, cases, routes, vehicles, agents
from agents.monitoring_agent import MonitoringAgent
import asyncio


app = FastAPI(
    title="Mwamko AI Disaster Response System",
    # description="Secure, disaster-aware routing, emergency case management, and resource allocation API.",
    description="AI-Powered emergency response coordination with agentic capabilities",
    version="2.0.0"
)

# Create database tables
Base.metadata.create_all(bind=engine)

# AI Agent Initialization
monitoring_agent = None

@app.on_event("startup")
async def startup_event():
    """Initialize AI agents on startup"""
    global monitoring_agent
    # Initialize monitoring agent
    monitoring_agent = MonitoringAgent(next(get_db()))
    
    # Start background monitoring task
    asyncio.create_task(background_monitoring())

async def background_monitoring():
    """Background task for continuous monitoring"""
    while True:
        if monitoring_agent:
            alerts = await monitoring_agent.monitor_emergencies()
            # Process alerts (send notifications, etc.)
            for alert in alerts:
                print(f"ALERT: {alert}")
        
        await asyncio.sleep(300)  # Check every 5 minutes

@app.get("/", tags=["System"])
def health_check():
    return {
        "status": "Healthy", 
        "service": "Mwamko AI - AI-Powered Disaster Response",
        "ai_capabilities": [
            "Emergency situation analysis",
            "Route optimization",
            "Predictive alerts", 
            "Resource allocation",
            "Real-time monitoring"
        ],
        "endpoints": {
            "auth": "/auth",
            "cases": "/cases", 
            "admin": "/route",
            "routes": "/cases/route",
            "vehicles": "/vehicles",
            "ai_agents": "/ai"
        }
    }

# Include routers
app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(admin.router)
app.include_router(routes.router)
app.include_router(agents.router)
app.include_router(vehicles.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
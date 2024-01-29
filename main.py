import gradio as gr
from fastapi import FastAPI
from pydantic import BaseModel
import requests


import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
from datetime import datetime
import os
from crewai import Crew
from textwrap import dedent
from dotenv import load_dotenv
from pydantic import BaseModel
import time
import threading

load_dotenv()

# Your existing imports and FinancialCrew class here...
from stock_analysis_agents import StockAnalysisAgents
from stock_analysis_tasks import StockAnalysisTasks

# initialize FastAPI
app = FastAPI()

# add Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# initialize Globals
class CompanyData(BaseModel):
    company: str

analysis_status = {}  # Global dictionary to store analysis status


# Define a function to run FastAPI with uvicorn
def run_fastapi():
    uvicorn.run(app, workers=1, host="127.0.0.1", port=8000)


# Implement Gradio Interface
# This step involves ensuring that the FastAPI application is correctly set up to receive and process
# requests from the Gradio interface.
# We use the following endpoints:  /analyze/, /status/{company}, and /result/{company} 

def analyze_stock(company_name, status):
    # setup FastAPI endpoints
    analyze_url = f"http://localhost:8000/analyze/"
    status_url = f"http://localhost:8000/status/{company_name}"
    result_url = f"http://localhost:8000/result/{company_name}"

    new_status = "Analyzing " + company_name + "..."

    # Trigger analysis
    analyze_response = requests.post(analyze_url, json={"company": company_name})
    if analyze_response.status_code != 200:
        return "Error initiating analysis", "No result"

    # Poll for status - simplified version
    while True:
        status_response = requests.get(status_url)
        if status_response.status_code != 200:
            return "Error checking status", "No result"
        status = status_response.json().get("status", "")
        if status == "Complete":
            break
        time.sleep(1)  # Simple polling mechanism, consider implementing a more sophisticated approach


    # Get result
    result_response = requests.get(result_url)
    if result_response.status_code == 200:
        result = result_response.json().get("result", "No result available")
    else:
        result = "Error retrieving result"

    # Update the status to indicate the analysis is complete
    new_status = "Analysis complete"
    
    return new_status, result

# Launch the Gradio Interface
# This will launch a web interface that communicates with the FastAPI backend.
# We Opt for gr.Blocks() over gr.Interface() as this  application requires a more complex UI, 
# multiple steps or stages, interactive elements that depend on each other, and because we want more control over the layout and flow of the application.
with gr.Blocks() as demo:
    gr.Markdown("## Stock Analyzer AI Agent")
    with gr.Row():
        company_input = gr.Textbox(label="Enter Company Name:")
        analyze_button = gr.Button("Analyze")
    status_output = gr.Textbox(label="Status", value="Waiting...", interactive=False)
    result_output = gr.Textbox(label="Result", interactive=False)
    status_state = gr.State(value="Waiting...")

    # When the button is clicked, call analyze_stock and update status and result
    analyze_button.click(
        fn=analyze_stock, 
        inputs=[company_input, status_state], 
        outputs=[status_state, result_output])

# Mount a gradio.Blocks to an existing FastAPI application.
    app = gr.mount_gradio_app(app, demo, path="/gradio")

# FastAPI Endpoints
#===================

# 1. Analyze Endpoint
# This endpoint will accept a POST request with the company name and initiate the analysis process. 
# It should immediately return a response indicating that the analysis has started.
@app.post("/analyze/")
async def analyze_company(company_data: CompanyData, background_tasks: BackgroundTasks):
    company = company_data.company
    # Start the analysis in the background
    background_tasks.add_task(run_analysis, company)
    return {"message": f"Analysis started for {company}"}

async def run_analysis(company):
    analysis_status[company] = "In Progress"
    try:
        financial_crew = FinancialCrew(company)
        result = financial_crew.run()

        # Ensure valid filename and handle file writing appropriately
        safe_company_name = "".join(x for x in company if x.isalnum())
        filename = f"{safe_company_name}_latest.txt"

        # Consider using an async file writer if you're handling large files or a high load
        with open(filename, "w") as file:
            file.write(result)
        analysis_status[company] = "Complete"

    except Exception as e:
        # Add logging or more sophisticated error handling here
        print(f"An error occurred: {e}")


# 2. Status Endpoint
# This endpoint returns the current status of the analysis for a given company. 
# Store the status in a global dictionary.    
@app.get("/status/{company}")
async def get_status(company: str):
    status = analysis_status.get(company, "Not Started")
    return {"status": status}

#3. Result Endpoint
# Once the analysis is complete, this endpoint provides the results. 
# The results are stored in a file.
@app.get("/result/{company}")
async def get_result(company: str):
    # Results are stored in a file named "{company}_result.txt"
    filename = f"{company}_result.txt"
    try:
        with open(filename, "r") as file:
            content = file.read()
        return {"result": content}
    except FileNotFoundError:
        return {"result": "Analysis not complete or file not found"}



# crewAI
#========

# FinancialCrew class and other necessary codes...
class FinancialCrew:
  def __init__(self, company):
    self.company = company

  def run(self):
    agents = StockAnalysisAgents()
    tasks = StockAnalysisTasks()

    research_analyst_agent = agents.research_analyst()
    financial_analyst_agent = agents.financial_analyst()
    investment_advisor_agent = agents.investment_advisor()

    research_task = tasks.research(research_analyst_agent, self.company)
    financial_task = tasks.financial_analysis(financial_analyst_agent)
    filings_task = tasks.filings_analysis(financial_analyst_agent)
    recommend_task = tasks.recommend(investment_advisor_agent)

    crew = Crew(
      agents=[
        research_analyst_agent,
        financial_analyst_agent,
        investment_advisor_agent
      ],
      tasks=[
        research_task,
        financial_task,
        filings_task,
        recommend_task
      ],
      verbose=True
    )

    result = crew.kickoff()
    return result


if __name__ == "__main__":

    # Start FastAPI in a separate thread
    fastapi_thread = threading.Thread(target=run_fastapi)
    fastapi_thread.daemon = True
    fastapi_thread.start()

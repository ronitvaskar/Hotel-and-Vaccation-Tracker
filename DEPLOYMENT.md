# PRJ-06 Deployment Guide

## Fastest public deployment: Render

This repository is prepared for a Render Web Service.

### 1. Push the project to GitHub

Create a new public repository, for example:
`prj-06-hotel-competitor-intelligence`

Upload all project files from this folder. Do not upload `.env`, `venv`, `node_modules`, or build output.

### 2. Create the Render service

In Render:
- New -> Web Service
- Connect the GitHub repository
- Runtime: Python
- Build Command: `python -m compileall .`
- Start Command: `python app.py`
- Health Check Path: `/api/health`
- Python version: 3.11.9

`render.yaml` already contains these settings if using Blueprint deployment.

### 3. First boot

If no database exists, the application automatically creates the labelled demonstration database. It contains the project demonstration data and does not claim to be live MakeMyTrip data.

### 4. Test after deployment

Open:
- `/` dashboard
- `/api/health`
- `/api/properties`
- `/api/conditions`
- `/api/dashboard`
- `/api/observations`
- `/api/changes`
- `/api/runs`
- `/api/export/observations.csv`

### 5. Important persistence note

Render's free service filesystem is ephemeral. The demonstration works without a persistent disk, but historical data collected after deployment can be lost after a service replacement/redeploy. For long-term tracking, use a managed PostgreSQL database or a persistent disk/database service.

For the examination demonstration, the seeded historical dataset is sufficient to demonstrate the application's analysis workflow. Live authorised observations should be imported using the CSV importer.

# Ticket Assignment Workflow

This application automatically processes new Autotask tickets, assigns them to technicians based on categories, and sends notifications to Microsoft Teams.

## Features

- Polls Autotask API every 5 minutes for new tickets
- Automatically assigns technicians based on ticket categories
- Sends notifications to Microsoft Teams
- Prevents duplicate processing using timestamp tracking
- Configurable category-to-technician mapping via CSV

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   - Copy `.env.template` to `.env`
   - Fill in your Autotask API credentials and Teams webhook URL

3. Update technician mapping:
   - Edit `technician_mapping.csv` to match your team structure
   - Format: category,technician,teams_mention

## Running the Application

```bash
python ticket_processor.py
```

## Configuration Files

- `.env`: API credentials and endpoints
- `technician_mapping.csv`: Category to technician mapping
- `last_processed.txt`: Tracks the last processed ticket timestamp (created automatically)

## Error Handling

The application includes error handling for:
- API failures
- Missing configurations
- Invalid mappings

Errors are logged to stdout for monitoring.

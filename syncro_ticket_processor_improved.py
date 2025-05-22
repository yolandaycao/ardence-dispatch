import os
import csv
import json
import time
import logging
import random
import schedule
import requests
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('syncro_processor.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

# Configuration
SYNCRO_API_URL = 'https://cloudavize.syncromsp.com/api/v1'
SYNCRO_API_KEY = os.getenv('SYNCRO_API_KEY')
TEAMS_BOT_URL = os.getenv('TEAMS_BOT_URL', 'https://3232-73-92-93-16.ngrok-free.app')
MAPPING_FILE = 'technician_mapping.json'
ASSIGNMENT_RESULTS_FILE = 'assignment_results.json'
PROCESSED_TICKETS_FILE = 'processed_tickets.json'

# Test mode settings
TEST_MODE = False  # Set to True to disable sending notifications
FORCE_TEST = True  # Set to True to force process one ticket for testing

# Track assignments for load balancing
LEVEL1_ASSIGNMENTS = {'Michael Barbin': 0, 'Jomaree Lawsin': 0}

def load_technician_mapping():
    """Load technician mapping from JSON file."""
    with open(MAPPING_FILE, 'r') as f:
        data = json.load(f)
    
    # Convert JSON structure to list of schedule entries
    mapping = []
    for tech_name, tech_info in data['technicians'].items():
        for schedule in tech_info['schedules']:
            entry = {
                'technician': tech_name,
                'email': tech_info['email'],
                'teams_mention': tech_info['teams_mention'],
                'days': schedule['days'],
                'start_time': schedule['start_time'],
                'end_time': schedule['end_time'],
                'categories': schedule['categories']
            }
            mapping.append(entry)
    
    return mapping

def load_processed_tickets():
    """Load the set of already processed ticket IDs."""
    try:
        if os.path.exists(PROCESSED_TICKETS_FILE):
            with open(PROCESSED_TICKETS_FILE, 'r') as f:
                return set(json.load(f))
        return set()
    except Exception as e:
        logging.error(f"Error loading processed tickets: {str(e)}")
        return set()

def save_processed_tickets(processed_tickets):
    """Save the set of processed ticket IDs."""
    try:
        with open(PROCESSED_TICKETS_FILE, 'w') as f:
            json.dump(list(processed_tickets), f)
    except Exception as e:
        logging.error(f"Error saving processed tickets: {str(e)}")

def get_new_tickets():
    """Get new tickets from Syncro API."""
    try:
        response = requests.get(
            f'{SYNCRO_API_URL}/tickets',
            headers={'Accept': 'application/json'},
            params={'api_key': SYNCRO_API_KEY}
        )
        response.raise_for_status()
        
        data = response.json()
        tickets = data.get('tickets', []) if isinstance(data, dict) else data
        
        if not isinstance(tickets, list):
            logging.error(f"Invalid tickets data format")
            return []
        
        # Get all unresolved tickets
        active_tickets = [t for t in tickets if isinstance(t, dict) 
                        and t.get('status') != 'Resolved']
        logging.info(f"Found {len(active_tickets)} active tickets")
        
        # In test mode, return the most recent active ticket
        if FORCE_TEST and active_tickets:
            logging.info("Test mode: Processing most recent active ticket")
            return [active_tickets[0]]
        
        # Load already processed tickets
        processed_tickets = load_processed_tickets()
        
        # Filter out already processed tickets
        new_tickets = [t for t in active_tickets if str(t.get('id')) not in processed_tickets]
        
        logging.info(f"Found {len(new_tickets)} new tickets to process")
        
        # Sort by created_at
        return sorted(new_tickets, key=lambda x: x.get('created_at', ''))
            
    except Exception as e:
        logging.error(f"Failed to get tickets: {e}")
        return []

def is_technician_available(tech_schedule):
    """Check if technician is available based on schedule."""
    # Get current time and day
    now = datetime.now()
    current_day = now.strftime('%a')
    current_time = now.strftime('%H:%M')
    
    # Parse schedule days
    days_range = tech_schedule['days'].split('-')
    if len(days_range) == 2:
        # Handle day ranges like Mon-Fri
        days_of_week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        start_idx = days_of_week.index(days_range[0])
        end_idx = days_of_week.index(days_range[1])
        
        # Handle wraparound (e.g., Sun-Thu)
        if end_idx < start_idx:
            end_idx += 7
            
        scheduled_days = [days_of_week[i % 7] for i in range(start_idx, end_idx + 1)]
        if current_day not in scheduled_days:
            return False
    else:
        # Handle specific days
        if current_day != tech_schedule['days']:
            return False
    
    # Check time range
    if current_time < tech_schedule['start_time'] or current_time > tech_schedule['end_time']:
        return False
    
    return True

def map_syncro_category(category):
    """Map Syncro ticket categories to our internal categories."""
    category = category.lower() if category else ''
    
    if 'account' in category or 'billing' in category:
        return 'Account Management'
    elif 'software' in category or 'application' in category:
        return 'Software'
    elif 'hardware' in category or 'printer' in category:
        return 'Hardware'
    elif 'network' in category or 'wifi' in category or 'internet' in category:
        return 'Network'
    elif 'server' in category or 'cloud' in category:
        return 'Server'
    elif 'security' in category or 'password' in category:
        return 'Security'
    else:
        return 'Level 1'  # Default category

def assign_technician(ticket, mapping):
    """Assign a technician to a ticket based on category and availability."""
    try:
        # Map ticket category
        ticket_category = map_syncro_category(ticket.get('problem_type', ''))
        
        # Get available technicians for this category
        available_techs = []
        level1_techs = []
        
        for entry in mapping:
            if is_technician_available(entry):
                if 'All' in entry['categories'] or ticket_category in entry['categories']:
                    available_techs.append(entry)
                    
                    # Track Level 1 technicians separately for load balancing
                    if 'Level 1' in entry['categories'] and entry['technician'] in LEVEL1_ASSIGNMENTS:
                        level1_techs.append(entry)
        
        # If no technicians are available, return "Needs human input"
        if not available_techs:
            return {'technician': 'Needs human input', 'teams_mention': None, 'email': None}
        
        # Special handling for Level 1 tickets - load balance between Michael and Jomaree
        if ticket_category == 'Level 1' and len(level1_techs) > 0:
            # Find the technician with the least assignments
            min_assignments = min(LEVEL1_ASSIGNMENTS.values())
            candidates = [tech for tech in level1_techs 
                         if LEVEL1_ASSIGNMENTS[tech['technician']] == min_assignments]
            
            # If multiple techs have the same count, choose randomly
            selected = random.choice(candidates)
            
            # Update assignment count
            LEVEL1_ASSIGNMENTS[selected['technician']] += 1
            
            return {
                'technician': selected['technician'],
                'teams_mention': selected['teams_mention'],
                'email': selected['email']
            }
        
        # For other categories, just pick the first available tech
        selected = available_techs[0]
        return {
            'technician': selected['technician'],
            'teams_mention': selected['teams_mention'],
            'email': selected['email']
        }
    except Exception as e:
        logging.error(f"Error assigning technician: {str(e)}")
        return {'technician': 'Needs human input', 'teams_mention': None, 'email': None}

# TODO: Read mode with Syncro only, no updates
# def update_ticket_assignment(ticket_id, technician):
#     """Update ticket assignment in Syncro."""
#     headers = {
#         'Authorization': SYNCRO_API_KEY,
#         'Content-Type': 'application/json'
#     }
#     
#     data = {
#         'ticket': {
#             'assigned_to': technician
#         }
#     }
#     
#     response = requests.put(
#         f'{SYNCRO_API_URL}/tickets/{ticket_id}',
#         headers=headers,
#         json=data
#     )
#     response.raise_for_status()

def save_assignment_result(ticket, assignment):
    """Save the ticket assignment result to a JSON file."""
    result = {
        'ticket_id': ticket.get('id'),
        'ticket_number': ticket.get('number'),
        'subject': ticket.get('subject'),
        'category': ticket.get('problem_type'),
        'assigned_to': assignment['technician'],
        'teams_mention': assignment['teams_mention'],
        'timestamp': datetime.now().isoformat(),
        'description': ticket.get('description'),
        'status': ticket.get('status'),
        'priority': ticket.get('priority')
    }
    
    try:
        # Load existing results
        if os.path.exists(ASSIGNMENT_RESULTS_FILE):
            with open(ASSIGNMENT_RESULTS_FILE, 'r') as f:
                results = json.load(f)
        else:
            results = []
        
        # Add new result
        results.append(result)
        
        # Save back to file
        with open(ASSIGNMENT_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2)
            
    except Exception as e:
        print(f"Error saving assignment result: {str(e)}")

def process_tickets():
    """Main function to process new tickets."""
    try:
        # Load technician mapping
        mapping = load_technician_mapping()
        if not mapping:
            logging.error("No technician mappings found")
            return
        
        # Get new unassigned tickets
        unassigned_tickets = get_new_tickets()
        if not unassigned_tickets:
            logging.info("No new tickets to process")
            return
        
        # Load processed tickets set
        processed_tickets = load_processed_tickets()
        
        # Process each ticket
        for ticket in unassigned_tickets:
            try:
                # Skip if already processed (double-check)
                if str(ticket.get('id')) in processed_tickets:
                    continue
                
                # Assign technician
                assignment = assign_technician(ticket, mapping)
                if not assignment:
                    continue
                
                # TODO: Update ticket in Syncro (currently disabled - read-only mode)
                # if assignment['technician'] != 'Needs human input':
                #     update_ticket_assignment(ticket['id'], assignment['technician'])
                
                # Save assignment result
                save_assignment_result(ticket, assignment)
                
                # Send Teams notification
                if assignment['technician'] != 'Needs human input' and not TEST_MODE:
                    send_teams_notification(ticket, assignment)
                elif TEST_MODE:
                    logging.info(f"TEST MODE: Would send notification for ticket #{ticket.get('number')} to {assignment['technician']}")
                
                # Mark ticket as processed
                processed_tickets.add(str(ticket.get('id')))
                
                logging.info(f"Processed ticket #{ticket.get('number')}: Assigned to {assignment['technician']}")
                    
            except Exception as e:
                logging.error(f"Error processing ticket {ticket.get('id', 'Unknown')}: {str(e)}")
        
        # Save updated processed tickets
        save_processed_tickets(processed_tickets)
                
    except Exception as e:
        logging.error(f"Error in process_tickets: {str(e)}")

def send_teams_notification(ticket, assignment):
    """Send notification to Teams bot."""
    try:
        notification_data = {
            "ticketId": ticket.get('number', str(ticket.get('id', 'Unknown'))),
            "assignedTo": assignment['technician'],
            "summary": ticket.get('subject', 'No subject')
        }
        
        # Send to Teams bot notification endpoint
        response = requests.post(
            f"{TEAMS_BOT_URL}/notify",
            json=notification_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            logging.info(f"Teams notification sent for ticket #{ticket.get('number')}: {response.text}")
        else:
            logging.error(f"Failed to send Teams notification: {response.status_code} - {response.text}")
            
    except Exception as e:
        logging.error(f"Error sending Teams notification: {str(e)}")

def main():
    """Main entry point."""
    logging.info("Starting Syncro ticket processor")
    
    # Schedule the job to run every 5 minutes
    schedule.every(5).minutes.do(process_tickets)
    
    # Run immediately on startup
    process_tickets()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()

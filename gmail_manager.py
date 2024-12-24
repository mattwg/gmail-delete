#!/usr/bin/env python3

import os
import pickle
import random
import argparse
from typing import List, Dict, Tuple
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from rich.console import Console
from rich.table import Table
from rich import print as rprint
import base64
import email
import webbrowser

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']  # Read, compose, send, modify, trash (but not permanent delete)

console = Console()

def get_gmail_service():
    """Gets or creates Gmail API service."""
    creds = None
    
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

def get_email_stats(service, age_range: str = 'recent') -> List[Tuple[str, int, List[str]]]:
    """Gets top 10 senders and their message IDs."""
    # First get user's email address
    profile = service.users().getProfile(userId='me').execute()
    user_email = profile['emailAddress']
    rprint(f"[yellow]Filtering emails for {user_email}...[/yellow]")
    
    # Define time periods based on age range
    if age_range == 'very-old':
        rprint("[yellow]Sampling very old messages (>10 years)...[/yellow]")
        periods = [
            ("ancient", "older_than:15y"),  # Older than 15 years
            ("very-old", "older_than:12y newer_than:15y"),  # 12-15 years ago
            ("old", "older_than:10y newer_than:12y"),  # 10-12 years ago
        ]
    elif age_range == 'old':
        rprint("[yellow]Sampling old messages (5-10 years)...[/yellow]")
        periods = [
            ("older", "older_than:8y newer_than:10y"),  # 8-10 years ago
            ("old", "older_than:6y newer_than:8y"),  # 6-8 years ago
            ("mid-old", "older_than:5y newer_than:6y"),  # 5-6 years ago
        ]
    else:  # recent
        rprint("[yellow]Sampling recent messages...[/yellow]")
        periods = [
            ("newer", "newer_than:1m"),  # Last month
            ("mid", "older_than:6m newer_than:7m"),  # 6-7 months ago
            ("old", "older_than:1y newer_than:13m")  # 12-13 months ago
        ]
    
    # Use a set to track unique message IDs
    message_ids_seen = set()
    all_messages = []
    
    for period_name, period_query in periods:
        rprint(f"[yellow]Sampling {period_name} messages...[/yellow]")
        # First try with unsubscribe patterns
        unsubscribe_query = (
            f'in:inbox {period_query} '  # Only look at inbox emails
            '-from:{user_email} '
            '(subject:"unsubscribe" OR '
            'subject:"subscription" OR '
            'subject:"newsletter" OR '
            'list-unsubscribe:* OR '  # Look for List-Unsubscribe header
            '"click here to unsubscribe" OR '
            '"to stop receiving" OR '
            '"opt out" OR '
            '"email preferences")'
        )
        results = service.users().messages().list(
            userId='me', 
            maxResults=167,  # Roughly 500/3 messages per period
            q=unsubscribe_query,
            fields='messages/id,nextPageToken'
        ).execute()
        
        if 'messages' in results:
            # Only add messages we haven't seen before
            for msg in results.get('messages', []):
                if msg['id'] not in message_ids_seen:
                    message_ids_seen.add(msg['id'])
                    all_messages.append(msg)
        
        # If we didn't get enough messages, try without unsubscribe patterns
        if len(all_messages) < 100:  # arbitrary threshold
            basic_query = f'in:inbox {period_query} -from:{user_email}'  # Only look at inbox emails
            results = service.users().messages().list(
                userId='me', 
                maxResults=167,  # Roughly 500/3 messages per period
                q=basic_query,
                fields='messages/id,nextPageToken'
            ).execute()
            
            if 'messages' in results:
                # Only add messages we haven't seen before
                for msg in results.get('messages', []):
                    if msg['id'] not in message_ids_seen:
                        message_ids_seen.add(msg['id'])
                        all_messages.append(msg)
            
    if not all_messages:
        return []
        
    rprint(f"[green]Analyzing {len(all_messages)} messages in detail[/green]")
    rprint("[yellow]Analyzing senders...[/yellow]")
    
    # Process messages in batches
    sender_stats: Dict[str, List[str]] = {}
    batch_size = 50  # Gmail API batch limit
    
    for i in range(0, len(all_messages), batch_size):
        batch = all_messages[i:i + batch_size]
        rprint(f"Processing messages {i+1}-{min(i+batch_size, len(all_messages))} of {len(all_messages)}...", end="\r")
        
        batch_request = service.new_batch_http_request()
        
        def callback(request_id, response, exception):
            if exception is None and 'payload' in response:
                headers = response['payload']['headers']
                from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), None)
                # Check for List-Unsubscribe header but don't require it
                has_unsubscribe = any(h['name'].lower() == 'list-unsubscribe' for h in headers)
                if from_header:  # Accept all senders now
                    if from_header not in sender_stats:
                        sender_stats[from_header] = []
                    sender_stats[from_header].append(request_id)
        
        for msg in batch:
            batch_request.add(
                service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'List-Unsubscribe']
                ),
                callback=callback,
                request_id=msg['id']
            )
            
        batch_request.execute()
    
    rprint("\n[green]Analysis complete![/green]")
    
    # Sort by volume and get top 10
    sorted_senders = sorted(sender_stats.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    
    return [(sender, len(msg_ids), msg_ids) for sender, msg_ids in sorted_senders]

def display_sender_list(sender_stats: List[Tuple[str, int, List[str]]]):
    """Displays formatted list of senders and counts."""
    table = Table(title="Top Email Senders")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Sender", style="green")
    table.add_column("Sample Count", justify="right", style="magenta")
    table.add_column("% of Sample", justify="right", style="yellow")
    
    # Use total sample size of 500
    TOTAL_SAMPLE_SIZE = 500
    
    for idx, (sender, count, _) in enumerate(sender_stats, 1):
        percentage = (count / TOTAL_SAMPLE_SIZE * 100)
        table.add_row(
            str(idx), 
            sender, 
            str(count),
            f"{percentage:.1f}%"
        )
    
    console.print(table)

def get_message_body(message: dict) -> str:
    """Extracts and decodes email message body."""
    if 'payload' not in message:
        return "No message body found."
        
    parts = [message['payload']]
    body = ""
    
    while parts:
        part = parts.pop(0)
        if 'body' in part and 'data' in part['body']:
            body += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        if 'parts' in part:
            parts.extend(part['parts'])
            
    return body or "No readable message body found."

def adaptive_batch_move(service, messages: list, operation_name: str = "messages") -> None:
    """Moves messages to trash with adaptive batch sizing."""
    if not messages:
        return
        
    total = len(messages)
    rprint(f"[yellow]Moving {total} {operation_name} to trash...[/yellow]")
    
    # Start with an aggressive batch size
    batch_size = 500
    min_batch_size = 50  # Don't go below this
    processed = 0
    consecutive_successes = 0
    consecutive_failures = 0
    
    while processed < total:
        try:
            end_idx = min(processed + batch_size, total)
            batch = messages[processed:end_idx]
            
            service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': [msg['id'] for msg in batch],
                    'addLabelIds': ['TRASH']
                }
            ).execute()
            
            batch_processed = len(batch)
            processed += batch_processed
            consecutive_successes += 1
            consecutive_failures = 0
            
            # Print progress first
            rprint(f"Progress: {processed}/{total} {operation_name} moved to trash (batch size: {batch_size})", end="\r")
            
            # If we've had several successes, try increasing batch size
            if consecutive_successes >= 3 and batch_size < 1000:
                old_size = batch_size
                batch_size = min(batch_size * 2, 1000)
                if old_size != batch_size:
                    rprint(f"\n[green]Increasing batch size to {batch_size}[/green]")
            
        except Exception as e:
            consecutive_failures += 1
            consecutive_successes = 0
            
            # Reduce batch size on failure
            old_size = batch_size
            batch_size = max(batch_size // 2, min_batch_size)
            rprint(f"\n[red]Error with batch size {old_size}: {str(e)}[/red]")
            rprint(f"[yellow]Reducing batch size to {batch_size} and retrying...[/yellow]")
            
            # If we've failed multiple times at minimum batch size, give up
            if consecutive_failures >= 3 and batch_size == min_batch_size:
                rprint(f"[red]Too many failures even at minimum batch size. Stopping.[/red]")
                break
                
    rprint(f"\n[green]Finished moving {processed} out of {total} {operation_name} to trash![/green]")

def move_to_trash(service, sender: str):
    """Moves all emails from a sender to trash."""
    # Extract email address from sender string if it contains one
    if '<' in sender and '>' in sender:
        email_address = sender[sender.find('<')+1:sender.find('>')]
    else:
        email_address = sender

    query = f'from:{email_address}'
    rprint(f"[yellow]Searching for emails from: {email_address}[/yellow]")
    
    messages = []
    next_page_token = None
    
    # Keep fetching pages until we have all messages
    while True:
        results = service.users().messages().list(
            userId='me', 
            q=query,
            pageToken=next_page_token,
            fields='messages/id,nextPageToken'  # Only get what we need
        ).execute()
        
        if 'messages' in results:
            messages.extend(results['messages'])
            
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break
    
    if not messages:
        rprint("[yellow]No messages found for this sender.[/yellow]")
        return
        
    adaptive_batch_move(service, messages, f"emails from {email_address}")

def empty_trash(service):
    """Permanently deletes all messages in the trash."""
    try:
        rprint("[yellow]Finding messages in trash...[/yellow]")
        messages = []
        next_page_token = None
        
        # Keep fetching pages until we have all trashed messages
        while True:
            results = service.users().messages().list(
                userId='me',
                q='in:trash',
                pageToken=next_page_token,
                fields='messages/id,nextPageToken'
            ).execute()
            
            if 'messages' in results:
                messages.extend(results['messages'])
                
            next_page_token = results.get('nextPageToken')
            if not next_page_token:
                break
        
        if not messages:
            rprint("[yellow]No messages found in trash.[/yellow]")
            return
            
        total = len(messages)
        rprint(f"[yellow]Permanently deleting {total} messages...[/yellow]")
        
        # Process in batches for efficiency
        batch_size = 25
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            for msg in batch:
                service.users().messages().delete(userId='me', id=msg['id']).execute()
            rprint(f"Progress: {min(i + batch_size, total)}/{total}", end="\r")
                
        rprint(f"\n[green]Successfully deleted {total} messages from trash![/green]")
        
    except Exception as e:
        rprint(f"[red]Error emptying trash: {str(e)}[/red]")

def move_category_to_trash(service, category: str):
    """Moves all emails from a category to trash."""
    query = f'category:{category.lower()}'
    rprint(f"[yellow]Moving emails from category: {category} to trash...[/yellow]")
    
    messages = []
    next_page_token = None
    
    # Keep fetching pages until we have all messages
    while True:
        results = service.users().messages().list(
            userId='me', 
            q=query,
            pageToken=next_page_token,
            fields='messages/id,nextPageToken'
        ).execute()
        
        if 'messages' in results:
            messages.extend(results['messages'])
            
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break
    
    if not messages:
        rprint("[yellow]No messages found in this category.[/yellow]")
        return
        
    adaptive_batch_move(service, messages, f"emails from category {category}")

def handle_category_menu(service, current_age_range: str):
    """Handles the category menu operations."""
    # Standard Gmail categories
    categories = ['Primary', 'Social', 'Promotions', 'Updates', 'Forums']
    
    # Display categories
    table = Table(title="Gmail Categories")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Category", style="green")
    
    for idx, category in enumerate(categories, 1):
        table.add_row(str(idx), category)
    
    console.print(table)
    
    # Ask if user wants to move any category to trash
    action = input("\nEnter category number to move to trash (or Enter to continue): ").strip()
    if action and action.isdigit():
        category_num = int(action)
        if 1 <= category_num <= len(categories):
            category = categories[category_num - 1]
            confirm = input(f"Are you sure you want to move all emails from {category} to trash? (y/N): ")
            if confirm.lower() == 'y':
                move_category_to_trash(service, category)

def adaptive_batch_archive(service, messages: list, operation_name: str = "messages") -> None:
    """Archives messages with adaptive batch sizing."""
    if not messages:
        return
        
    total = len(messages)
    rprint(f"[yellow]Archiving {total} {operation_name}...[/yellow]")
    
    # Start with an aggressive batch size
    batch_size = 500
    min_batch_size = 50  # Don't go below this
    processed = 0
    consecutive_successes = 0
    consecutive_failures = 0
    
    while processed < total:
        try:
            end_idx = min(processed + batch_size, total)
            batch = messages[processed:end_idx]
            
            service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': [msg['id'] for msg in batch],
                    'removeLabelIds': ['INBOX']  # Removing INBOX label archives the message
                }
            ).execute()
            
            batch_processed = len(batch)
            processed += batch_processed
            consecutive_successes += 1
            consecutive_failures = 0
            
            # Print progress first
            rprint(f"Progress: {processed}/{total} {operation_name} archived (batch size: {batch_size})", end="\r")
            
            # If we've had several successes, try increasing batch size
            if consecutive_successes >= 3 and batch_size < 1000:
                old_size = batch_size
                batch_size = min(batch_size * 2, 1000)
                if old_size != batch_size:
                    rprint(f"\n[green]Increasing batch size to {batch_size}[/green]")
            
        except Exception as e:
            consecutive_failures += 1
            consecutive_successes = 0
            
            # Reduce batch size on failure
            old_size = batch_size
            batch_size = max(batch_size // 2, min_batch_size)
            rprint(f"\n[red]Error with batch size {old_size}: {str(e)}[/red]")
            rprint(f"[yellow]Reducing batch size to {batch_size} and retrying...[/yellow]")
            
            # If we've failed multiple times at minimum batch size, give up
            if consecutive_failures >= 3 and batch_size == min_batch_size:
                rprint(f"[red]Too many failures even at minimum batch size. Stopping.[/red]")
                break
                
    rprint(f"\n[green]Finished archiving {processed} out of {total} {operation_name}![/green]")

def archive_emails(service, sender: str):
    """Archives all emails from a sender."""
    # Extract email address from sender string if it contains one
    if '<' in sender and '>' in sender:
        email_address = sender[sender.find('<')+1:sender.find('>')]
    else:
        email_address = sender

    query = f'from:{email_address} in:inbox'  # Only archive emails that are in inbox
    rprint(f"[yellow]Searching for emails from: {email_address}[/yellow]")
    
    messages = []
    next_page_token = None
    
    # Keep fetching pages until we have all messages
    while True:
        results = service.users().messages().list(
            userId='me', 
            q=query,
            pageToken=next_page_token,
            fields='messages/id,nextPageToken'  # Only get what we need
        ).execute()
        
        if 'messages' in results:
            messages.extend(results['messages'])
            
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break
    
    if not messages:
        rprint("[yellow]No messages found in inbox for this sender.[/yellow]")
        return
        
    adaptive_batch_archive(service, messages, f"emails from {email_address}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Gmail Manager - Analyze and clean up your Gmail inbox')
    parser.add_argument('--age', '-a', choices=['recent', 'old', 'very-old'], default='recent',
                       help='Age range of emails to analyze: recent (default), old (5-10 years), or very-old (>10 years)')
    args = parser.parse_args()

    rprint("[yellow]Starting Gmail Manager...[/yellow]")
    try:
        rprint("[yellow]Authenticating with Gmail...[/yellow]")
        service = get_gmail_service()
        rprint("[green]Authentication successful![/green]")
    except Exception as e:
        rprint("[red]Failed to authenticate with Gmail API. Make sure credentials.json is present.[/red]")
        rprint(f"[red]Error: {str(e)}[/red]")
        return

    # Get initial stats with specified age range
    sender_stats = get_email_stats(service, age_range=args.age)
    if not sender_stats:
        rprint("[yellow]No emails found![/yellow]")
        return

    while True:
        display_sender_list(sender_stats)
        
        rprint("\n[cyan]Options:[/cyan]")
        rprint("1-10: View emails from sender")
        rprint("D: Delete all emails from a sender")
        rprint("M: Delete emails from multiple senders")
        rprint("A: Archive emails from multiple senders")
        rprint("R: Refresh list")
        rprint("C: Manage categories")
        rprint("Q: Quit")
        
        choice = input("\nEnter your choice: ").strip()
        
        if choice.lower() == 'q':
            break
            
        if choice.lower() == 'r':
            sender_stats = get_email_stats(service, age_range=args.age)
            if not sender_stats:
                rprint("[yellow]No emails found![/yellow]")
                break
            continue
            
        if choice.lower() == 'd':
            try:
                sender_num = int(input("Enter the sender number (1-10) to delete all their emails: ").strip())
                if 1 <= sender_num <= len(sender_stats):
                    sender = sender_stats[sender_num - 1][0]
                    confirm = input(f"Are you sure you want to move all emails from {sender} to trash? (y/N): ")
                    if confirm.lower() == 'y':
                        move_to_trash(service, sender)
                        # Refresh stats after deletion, maintaining age range
                        sender_stats = get_email_stats(service, age_range=args.age)
                        if not sender_stats:
                            rprint("[yellow]No more senders in the list![/yellow]")
                            break
            except ValueError:
                rprint("[red]Please enter a valid number.[/red]")
            continue

        if choice.lower() == 'm':
            try:
                input_str = input("Enter sender numbers (1-10 or 'ALL' or 'ALL -1 -2' to exclude): ").strip()
                selected_senders = []
                
                if input_str.upper().startswith('ALL'):
                    # Get all numbers except those prefixed with '-'
                    excluded = {abs(int(n)) for n in input_str.split()[1:] if n.startswith('-')}
                    selected_senders = [
                        sender_stats[i][0] for i in range(len(sender_stats))
                        if i + 1 not in excluded
                    ]
                else:
                    # Process individual numbers
                    numbers = input_str.split()
                    # Validate all numbers before proceeding
                    for num in numbers:
                        sender_num = int(num)
                        if 1 <= sender_num <= len(sender_stats):
                            selected_senders.append(sender_stats[sender_num - 1][0])
                        else:
                            rprint(f"[red]Invalid sender number: {num}[/red]")
                            selected_senders = []
                            break
                
                if selected_senders:
                    # Show summary of selected senders
                    rprint("\n[yellow]Selected senders:[/yellow]")
                    for sender in selected_senders:
                        rprint(f"- {sender}")
                    
                    confirm = input(f"\nAre you sure you want to move all emails from these {len(selected_senders)} senders to trash? (y/N): ")
                    if confirm.lower() == 'y':
                        for sender in selected_senders:
                            rprint(f"\n[yellow]Processing {sender}...[/yellow]")
                            move_to_trash(service, sender)
                        
                        # Refresh stats after all deletions, maintaining age range
                        sender_stats = get_email_stats(service, age_range=args.age)
                        if not sender_stats:
                            rprint("[yellow]No more senders in the list![/yellow]")
                            break
            except ValueError:
                rprint("[red]Please enter valid numbers or 'ALL' with optional exclusions (e.g., 'ALL -1 -2').[/red]")
            continue
            
        if choice.lower() == 'a':
            try:
                input_str = input("Enter sender numbers (1-10 or 'ALL' or 'ALL -1 -2' to exclude): ").strip()
                selected_senders = []
                
                if input_str.upper().startswith('ALL'):
                    # Get all numbers except those prefixed with '-'
                    excluded = {abs(int(n)) for n in input_str.split()[1:] if n.startswith('-')}
                    selected_senders = [
                        sender_stats[i][0] for i in range(len(sender_stats))
                        if i + 1 not in excluded
                    ]
                else:
                    # Process individual numbers
                    numbers = input_str.split()
                    # Validate all numbers before proceeding
                    for num in numbers:
                        sender_num = int(num)
                        if 1 <= sender_num <= len(sender_stats):
                            selected_senders.append(sender_stats[sender_num - 1][0])
                        else:
                            rprint(f"[red]Invalid sender number: {num}[/red]")
                            selected_senders = []
                            break
                
                if selected_senders:
                    # Show summary of selected senders
                    rprint("\n[yellow]Selected senders:[/yellow]")
                    for sender in selected_senders:
                        rprint(f"- {sender}")
                    
                    confirm = input(f"\nAre you sure you want to archive all emails from these {len(selected_senders)} senders? (y/N): ")
                    if confirm.lower() == 'y':
                        for sender in selected_senders:
                            rprint(f"\n[yellow]Processing {sender}...[/yellow]")
                            archive_emails(service, sender)
                        
                        # Refresh stats after all archives
                        sender_stats = get_email_stats(service, age_range=args.age)
                        if not sender_stats:
                            rprint("[yellow]No more senders in the list![/yellow]")
                            break
            except ValueError:
                rprint("[red]Please enter valid numbers or 'ALL' with optional exclusions (e.g., 'ALL -1 -2').[/red]")
            continue
            
        if choice.lower() == 'c':
            handle_category_menu(service, args.age)
            continue
            
        # Handle viewing emails for a sender
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sender_stats):
                sender, _, message_ids = sender_stats[idx]
                # Get 3 random sample emails
                sample_ids = random.sample(message_ids, min(3, len(message_ids)))
                
                # First show a list of the sample emails
                rprint(f"\n[cyan]Sample emails from {sender}:[/cyan]")
                for i, msg_id in enumerate(sample_ids, 1):
                    message = service.users().messages().get(
                        userId='me', 
                        id=msg_id, 
                        format='metadata',
                        metadataHeaders=['Subject', 'Date']
                    ).execute()
                    
                    headers = message['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'No Date')
                    
                    rprint(f"{i}. Subject: {subject}")
                    rprint(f"   Date: {date}\n")
                
                # Let user choose which email to open
                email_choice = input("\nEnter number to open in browser (or press Enter to skip): ").strip()
                if email_choice and email_choice.isdigit():
                    email_idx = int(email_choice) - 1
                    if 0 <= email_idx < len(sample_ids):
                        url = f"https://mail.google.com/mail/u/0/#inbox/{sample_ids[email_idx]}"
                        webbrowser.open(url)
                
        except ValueError:
            rprint("[red]Invalid choice. Please try again.[/red]")
            
if __name__ == '__main__':
    main() 
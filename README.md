# Gmail Manager

A command-line tool to help manage and clean up your Gmail inbox by analyzing email patterns and bulk-deleting unwanted messages.

## Features

- Analyzes email patterns across different time periods:
  - Recent mode (default):
    - Recent emails (last month)
    - Mid-range emails (6-7 months ago)
    - Older emails (12-13 months ago)
  - Old mode (5-10 years):
    - Older emails (8-10 years ago)
    - Old emails (6-8 years ago)
    - Mid-old emails (5-6 years ago)
  - Very-old mode (>10 years):
    - Ancient emails (>15 years)
    - Very old emails (12-15 years ago)
    - Old emails (10-12 years ago)
- Smart detection of newsletter and subscription emails:
  - Finds emails with unsubscribe links
  - Detects common newsletter patterns
  - Identifies List-Unsubscribe headers
- Shows top 10 email senders with statistics
- Allows viewing sample emails from each sender
- Bulk move to trash for all emails from a specific sender
- Multiple sender deletion with flexible selection:
  - Select individual senders (e.g., "1 2 3")
  - Select all senders except specific ones (e.g., "ALL -1 -2")
- Opens selected emails directly in your browser
- Progress tracking for long operations
- Efficient batch processing to handle large numbers of emails

## Example Output

```
Starting Gmail Manager...
Authenticating with Gmail...
Authentication successful!
Filtering emails for user@gmail.com...
Sampling very old messages (>10 years)...
Sampling ancient messages...
Sampling very-old messages...
Sampling old messages...
Analyzing 436 messages in detail
Analyzing senders...
Analysis complete!

                                       Top Email Senders                                        
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃  # ┃ Sender                                                     ┃ Sample Count ┃ % of Sample ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│  1 │ Glassdoor Jobs <noreply@glassdoor.com>                     │           12 │        2.4% │
│  2 │ LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>       │           10 │        2.0% │
│  3 │ Reddit <noreply@redditmail.com>                            │            8 │        1.6% │
│  4 │ MIT Technology Review <promotions@technologyreview.com>     │            7 │        1.4% │
│  5 │ The Feed <hello@thefeed.com>                               │            7 │        1.4% │
│  6 │ Ministry of Supply <hello@ministryofsupply.com>            │            6 │        1.2% │
│  7 │ ZINIO <zinio@discover.zinio.com>                           │            6 │        1.2% │
│  8 │ Your PM Report <e-news@email.bayareanewsgroup.com>         │            5 │        1.0% │
│  9 │ From You Flowers <FromYouFlowers@email.fromyouflowers.com> │            5 │        1.0% │
│ 10 │ Brian Moran @ CreatorU <hello@creatoru.com>                │            4 │        0.8% │
└────┴────────────────────────────────────────────────────────────┴──────────────┴─────────────┘

Options:
1-10: View emails from sender
D: Delete all emails from a sender
M: Delete emails from multiple senders
R: Refresh list
Q: Quit

Enter your choice: M
Enter sender numbers (1-10 or 'ALL' or 'ALL -1 -2' to exclude): ALL -2 -3

Selected senders:
- Glassdoor Jobs <noreply@glassdoor.com>
- MIT Technology Review <promotions@technologyreview.com>
- The Feed <hello@thefeed.com>
- Ministry of Supply <hello@ministryofsupply.com>
- ZINIO <zinio@discover.zinio.com>
- Your PM Report <e-news@email.bayareanewsgroup.com>
- From You Flowers <FromYouFlowers@email.fromyouflowers.com>
- Brian Moran @ CreatorU <hello@creatoru.com>

Are you sure you want to move all emails from these 8 senders to trash? (y/N):
```

## Setup

1. Enable the Gmail API:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project or select an existing one
   - Enable the Gmail API
   - Create OAuth 2.0 credentials
   - Download the credentials and save as `credentials.json` in the project directory

2. Install dependencies:
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client rich
```

## Usage

Run the script:
```bash
# Normal mode (recent emails)
python gmail_manager.py

# Old emails mode (5-10 years old)
python gmail_manager.py --age old
# or
python gmail_manager.py -a old

# Very old emails mode (>10 years old)
python gmail_manager.py --age very-old
# or
python gmail_manager.py -a very-old
```

The tool will:
1. Authenticate with your Gmail account (first time only)
2. Display a list of your top email senders with statistics
3. Provide options to:
   - View sample emails from any sender (1-10)
   - Delete all emails from a sender (D)
   - Delete emails from multiple senders (M)
     - Enter specific numbers: "1 2 3"
     - Enter "ALL" for all senders
     - Enter "ALL -1 -2" to select all except specific senders
   - Refresh the analysis (R)
   - Quit the program (Q)

## Notes

- The tool samples approximately 500 emails across three time periods for analysis
- Focuses on finding newsletter and subscription emails with unsubscribe options
- When deleting emails, they are moved to trash (not permanently deleted)
- The tool requires read and modify permissions for your Gmail account
- Authentication tokens are stored locally in `token.pickle`
- Use `--age` or `-a` to specify the age range of emails to analyze:
  - `recent`: Last year (default)
  - `old`: 5-10 years old
  - `very-old`: Over 10 years old

## Security

- Your credentials are stored locally in `credentials.json`
- The authentication token is stored locally in `token.pickle`
- No email content is stored permanently
- The tool uses official Google API libraries for all operations
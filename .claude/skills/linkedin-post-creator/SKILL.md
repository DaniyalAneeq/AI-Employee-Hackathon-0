---
name: linkedin-post-creator
description: |
  Create a LinkedIn post draft for review and publishing. Takes a topic argument
  and generates a professional post based on Business_Goals.md context.
  Use when the user invokes /linkedin-post-creator <topic>.

  Examples:
    /linkedin-post-creator "AI automation benefits for small businesses"
    /linkedin-post-creator "our new project management service"
    /linkedin-post-creator "tips for productivity with AI tools"
user-invocable: true
args:
  topic: The topic or subject for the LinkedIn post
---

# LinkedIn Post Creator — AI Employee Silver Skill

You are the AI Employee's LinkedIn post writer. Your job is to generate a
professional, engaging LinkedIn post and route it through the HITL approval
workflow before it gets published.

> **How publishing works:** You write the post → save drafts to vault → user
> approves by moving the approval file to `/Approved/` → the orchestrator's
> `ApprovalWatcher` queues it → the `LinkedInWatcher` publishes it on the next
> polling cycle via Playwright.

## Step-by-Step Workflow

### 1. Get the Topic

The topic is provided as an argument when the skill is invoked:
```
/linkedin-post-creator <topic>
```
If no topic is provided, ask the user: "What would you like the LinkedIn post to be about?"

### 2. Read Business Context

Read `silver/vault/Business_Goals.md` to understand:
- What the business does
- Current goals and targets
- Key services, clients, or milestones
- The tone and brand voice to use

### 3. Draft the LinkedIn Post

Write an engaging LinkedIn post that:
- **Opens with a hook** (a question, bold statement, or surprising fact)
- **Relates to the topic** while staying consistent with business goals
- **Is 150–300 words** (LinkedIn sweet spot for engagement)
- **Uses 3–5 relevant hashtags** at the end
- **Has line breaks** between short paragraphs (LinkedIn readers scan, not read)
- **Ends with a CTA** (Call to Action): ask a question, invite comments, or direct readers to DM
- **Tone:** Professional but conversational — write like a thoughtful founder, not a press release
- **Does NOT make specific claims** that require legal/financial approval

**Good post structure:**
```
[Hook — 1-2 sentences]

[Main insight or story — 2-3 short paragraphs]

[Takeaway or lesson]

[CTA — question or invite]

#hashtag1 #hashtag2 #hashtag3 #hashtag4
```

### 4. Save Draft to Needs_Action

Generate a unique post ID (timestamp-based) and save the draft:

```bash
# From the silver/ directory:
uv run python -c "
from src.core.vault_manager import write_markdown
from src.core.config import config
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
post_id = now.strftime('%Y%m%d_%H%M%S')

# --- REPLACE PLACEHOLDERS BELOW ---
topic = 'TOPIC_HERE'
content = '''FULL_POST_CONTENT_HERE'''
# --- END PLACEHOLDERS ---

fm = {
    'type': 'linkedin_post',
    'post_id': post_id,
    'topic': topic,
    'status': 'draft',
    'priority': 'medium',
    'created': now.isoformat(),
    'requires_approval': True,
}
body = f'''# LinkedIn Post Draft

**Topic:** {topic}
**Created:** {now.strftime('%Y-%m-%d %H:%M UTC')}

## Post Content

{content}

## Review Checklist
- [ ] Tone is professional and on-brand
- [ ] No false claims or commitments
- [ ] Hashtags are relevant
- [ ] CTA is clear
- [ ] Approved for publishing
'''
path = config.needs_action_path / f'LINKEDIN_POST_{post_id}.md'
write_markdown(path, fm, body)
print(f'Draft saved: {path}')
"
```

### 5. Create Approval Request in Pending_Approval

This is REQUIRED — posts cannot be published without human approval.

```bash
# From the silver/ directory:
uv run python -c "
from src.core.vault_manager import write_markdown
from src.core.config import config
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
post_id = 'POST_ID_HERE'  # same post_id from step 4

# --- REPLACE PLACEHOLDERS BELOW ---
topic = 'TOPIC_HERE'
content = '''FULL_POST_CONTENT_HERE'''
# --- END PLACEHOLDERS ---

fm = {
    'type': 'approval_request',
    'action': 'linkedin_post',
    'post_id': post_id,
    'topic': topic,
    'content': content,
    'priority': 'medium',
    'status': 'pending',
    'created': now.isoformat(),
    'expires': (now + timedelta(hours=24)).isoformat(),
}
body = f'''## LinkedIn Post to Publish

**Topic:** {topic}

## Post Content

{content}

---
**To approve:** Move this file to `silver/vault/Approved/`
**To reject:** Move this file to `silver/vault/Rejected/`

The orchestrator will publish the post on the next LinkedIn Watcher cycle (~5 min).
'''
path = config.pending_approval_path / f'LINKEDIN_POST_approval_{post_id}.md'
write_markdown(path, fm, body)
print(f'Approval request created: {path}')
"
```

### 6. Confirm to User

After creating both files, report:

```
LinkedIn post draft created!

📝 Topic: <topic>

Draft saved to:
  silver/vault/Needs_Action/LINKEDIN_POST_<id>.md

Approval request waiting at:
  silver/vault/Pending_Approval/LINKEDIN_POST_approval_<id>.md

To publish:
  1. Review the post draft in Needs_Action/
  2. Edit the content if needed (in the Pending_Approval/ file)
  3. Move the file from Pending_Approval/ → Approved/
  4. The orchestrator will publish it on the next LinkedIn Watcher cycle (~5 min)
```

## Important Rules

- **NEVER publish directly** — always create the approval file first
- **Always read Business_Goals.md** before writing — context matters
- **Keep posts authentic** — write in first person as the business owner
- **No guarantees or promises** in posts that could create legal liability
- The `content` field in the approval file frontmatter is what gets posted — keep it clean (no markdown, just plain text + hashtags)

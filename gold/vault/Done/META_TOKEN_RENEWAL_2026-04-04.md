---
type: maintenance_action
action: configure_meta_page_token
priority: high
status: needs_human
created: "2026-04-04T00:12:00Z"
blocked_items:
  - "Approved/META_FACEBOOK_6a0c5de5.md (Gold Tier launch post — ready to publish)"
  - "Pending_Approval/META_INSTAGRAM_366e581c.md (needs approval + image)"
page_name: "AI Automation"
page_id: "948068851733871"
---

## Meta Page Token Configuration Required

**Why:** The current token in `gold/.env` is a **User Access Token**, not a **Page Access Token**.
Facebook's Graph API requires a Page Access Token to publish posts to a Page.

The "AI Automation" page (ID: 948068851733871) exists and is reachable, but the AI cannot
post to it until a proper Page Access Token is configured.

## Steps to Get a Page Access Token

### Option A — Graph API Explorer (Quickest)
1. Go to [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. Select your app from the dropdown
3. Click **Generate Access Token**
4. In the **User or Page** dropdown, select **"AI Automation"** (your page)
5. Add permissions: `pages_manage_posts`, `pages_read_engagement`
6. Click **Generate** — this gives you a SHORT-LIVED page token (~1 hour)
7. To extend it to 60 days, use the [Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/) → click **Extend Access Token**

### Option B — Exchange Existing User Token
If your user token has `pages_show_list` permission:
```bash
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_USER_TOKEN"
# Returns page tokens for all pages you manage
# Look for the "AI Automation" page entry and copy its access_token
```

## Update the .env File
```bash
# Edit gold/.env:
META_PAGE_ACCESS_TOKEN=<new_page_access_token>
```

## Verify It Works
```bash
node /tmp/check_token.mjs  # Should show type: "PAGE" and valid: true
```

## After Updating
Move this file to `gold/vault/Done/` and re-run `/meta-social-poster`.
The Gold Tier launch post will publish immediately.

---

**Note:** Page Access Tokens from the Graph API Explorer last ~60 days.
Set a calendar reminder: next renewal due ~**2026-06-04**.
For permanent automation, use a System User token via Meta Business Suite.

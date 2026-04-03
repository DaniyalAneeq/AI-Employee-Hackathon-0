/**
 * meta-social-mcp — MCP Server for Facebook & Instagram (Meta Graph API)
 *
 * Tools exposed:
 *   post_to_facebook          — Post a message (+ optional image) to a Facebook Page
 *   post_to_instagram         — Post a message (+ optional image) to an Instagram Business account
 *   generate_summary_of_posts — Fetch post metrics for the last N days
 *
 * Configuration (env vars):
 *   META_PAGE_ID          — Facebook Page ID
 *   META_PAGE_ACCESS_TOKEN— Facebook Page access token (long-lived)
 *   META_IG_USER_ID       — Instagram Business Account ID (linked to page)
 *   META_GRAPH_API_VERSION— e.g. "v19.0" (default)
 *   DRY_RUN               — "true" to skip actual API calls (logs only)
 *
 * Reference:
 *   Facebook: https://developers.facebook.com/docs/pages/publishing/
 *   Instagram: https://developers.facebook.com/docs/instagram-api/reference/ig-user/media
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { readFileSync, existsSync, createReadStream } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import FormData from "form-data";

// Load .env from gold/ directory
const __dirname = dirname(fileURLToPath(import.meta.url));
const envPath = resolve(__dirname, "../../.env");
if (existsSync(envPath)) {
  const envContent = readFileSync(envPath, "utf8");
  for (const line of envContent.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) process.env[key] = val;
  }
}

// ── Configuration ──────────────────────────────────────────────────────────────
const PAGE_ID = process.env.META_PAGE_ID || "";
const PAGE_TOKEN = process.env.META_PAGE_ACCESS_TOKEN || "";
const IG_USER_ID = process.env.META_IG_USER_ID || "";
const GRAPH_VERSION = process.env.META_GRAPH_API_VERSION || "v19.0";
const GRAPH_BASE = `https://graph.facebook.com/${GRAPH_VERSION}`;
const DRY_RUN = process.env.DRY_RUN?.toLowerCase() === "true";

// ── Helpers ────────────────────────────────────────────────────────────────────

function requireConfig(...keys) {
  const missing = keys.filter((k) => !process.env[k] && !["META_PAGE_ID","META_PAGE_ACCESS_TOKEN","META_IG_USER_ID"].includes(k) || (k === "META_PAGE_ID" && !PAGE_ID) || (k === "META_PAGE_ACCESS_TOKEN" && !PAGE_TOKEN) || (k === "META_IG_USER_ID" && !IG_USER_ID));
  if (missing.length > 0) {
    throw new Error(
      `Missing required env vars: ${missing.join(", ")}. Set them in gold/.env`
    );
  }
}

async function graphGet(path, params = {}) {
  const url = new URL(`${GRAPH_BASE}/${path}`);
  url.searchParams.set("access_token", PAGE_TOKEN);
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, String(v));
  }
  const resp = await fetch(url.toString());
  const data = await resp.json();
  if (data.error) throw new Error(`Graph API: ${data.error.message}`);
  return data;
}

async function graphPost(path, body) {
  const url = new URL(`${GRAPH_BASE}/${path}`);
  url.searchParams.set("access_token", PAGE_TOKEN);
  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (data.error) throw new Error(`Graph API: ${data.error.message}`);
  return data;
}

// ── Tool Implementations ───────────────────────────────────────────────────────

/**
 * post_to_facebook — publishes a post to a Facebook Page
 */
async function postToFacebook(message, imagePath = null) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      message: `[DRY RUN] Would post to Facebook Page ${PAGE_ID || "UNSET"}: "${message.slice(0, 80)}..."`,
      image: imagePath || "none",
    };
  }

  requireConfig("META_PAGE_ID", "META_PAGE_ACCESS_TOKEN");

  let postId;

  if (imagePath && existsSync(imagePath)) {
    // Photo post via multipart upload
    const form = new FormData();
    form.append("message", message);
    form.append("source", createReadStream(imagePath));
    form.append("access_token", PAGE_TOKEN);

    const url = `${GRAPH_BASE}/${PAGE_ID}/photos`;
    const resp = await fetch(url, { method: "POST", body: form });
    const data = await resp.json();
    if (data.error) throw new Error(`Graph API: ${data.error.message}`);
    postId = data.id;
  } else {
    // Text-only post
    const result = await graphPost(`${PAGE_ID}/feed`, { message });
    postId = result.id;
  }

  return {
    success: true,
    platform: "facebook",
    post_id: postId,
    page_id: PAGE_ID,
    message_preview: message.slice(0, 100),
    has_image: !!imagePath,
    url: `https://www.facebook.com/${postId?.replace("_", "/posts/")}`,
    published_at: new Date().toISOString(),
  };
}

/**
 * post_to_instagram — publishes to Instagram Business account
 * Uses the 2-step container + publish flow.
 */
async function postToInstagram(message, imagePath = null) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      message: `[DRY RUN] Would post to Instagram (user ${IG_USER_ID || "UNSET"}): "${message.slice(0, 80)}..."`,
      image: imagePath || "none",
    };
  }

  requireConfig("META_IG_USER_ID", "META_PAGE_ACCESS_TOKEN");

  // Instagram requires an image URL or video. For text-only (no image),
  // we must use the Reels or Stories endpoint, which requires a video.
  // The standard /media endpoint requires image_url or video_url.
  // If no image provided, we post a "text card" as a note (if available)
  // or use a placeholder approach and log a warning.

  if (!imagePath) {
    // Instagram does not support text-only posts via Graph API without a media file.
    // We return a structured message that tells the caller to provide an image.
    return {
      success: false,
      platform: "instagram",
      error:
        "Instagram Graph API requires an image or video for all posts. Please provide image_path.",
      suggestion:
        "Create an image with the text overlaid, then call post_to_instagram with image_path set.",
      caption_preview: message.slice(0, 100),
    };
  }

  if (!existsSync(imagePath)) {
    throw new Error(`Image file not found: ${imagePath}`);
  }

  // Step 1: Upload media (requires publicly accessible URL in production;
  // for local files we'd need to host them first).
  // NOTE: In production, image must be a public HTTPS URL.
  // We'll use the fb_url approach via Facebook's /photos endpoint for page-linked IG.

  // For local dev, we use the page photo as the IG image source
  const fbPhotoResult = await postToFacebook(message, imagePath);

  // Step 2: Create IG media container using the FB photo URL
  // This requires the photo to be published publicly (Facebook handles it)
  // Using the page photo ID to link to IG
  const imageUrl = `https://www.facebook.com/photo?fbid=${fbPhotoResult.post_id?.split("_")[1]}&set=a.${fbPhotoResult.post_id?.split("_")[0]}`;

  const container = await graphPost(`${IG_USER_ID}/media`, {
    image_url: imageUrl,
    caption: message,
  });

  if (!container.id) {
    throw new Error("Failed to create Instagram media container");
  }

  // Step 3: Publish the container
  const published = await graphPost(`${IG_USER_ID}/media_publish`, {
    creation_id: container.id,
  });

  return {
    success: true,
    platform: "instagram",
    media_id: published.id,
    ig_user_id: IG_USER_ID,
    caption_preview: message.slice(0, 100),
    has_image: true,
    facebook_post_id: fbPhotoResult.post_id,
    published_at: new Date().toISOString(),
  };
}

/**
 * generate_summary_of_posts — fetches post insights for the last N days
 */
async function generateSummaryOfPosts(lastDays = 7) {
  if (DRY_RUN) {
    return {
      dry_run: true,
      period_days: lastDays,
      facebook: {
        posts: [
          {
            id: "FB_123",
            message: "Sample AI automation post #AIEmployee",
            created_time: new Date().toISOString(),
            likes: 42,
            comments: 7,
            shares: 3,
          },
        ],
      },
      instagram: {
        posts: [
          {
            id: "IG_456",
            caption: "Building autonomous AI employees...",
            timestamp: new Date().toISOString(),
            like_count: 89,
            comments_count: 12,
          },
        ],
      },
      summary: "DRY_RUN — no real API calls made",
    };
  }

  requireConfig("META_PAGE_ID", "META_PAGE_ACCESS_TOKEN");

  const since = Math.floor(Date.now() / 1000 - lastDays * 86400);

  // Facebook posts
  let fbPosts = [];
  try {
    const fbResult = await graphGet(`${PAGE_ID}/posts`, {
      fields: "id,message,created_time,likes.summary(true),comments.summary(true),shares",
      since,
      limit: 25,
    });
    fbPosts = (fbResult.data || []).map((p) => ({
      id: p.id,
      message: (p.message || "").slice(0, 100),
      created_time: p.created_time,
      likes: p.likes?.summary?.total_count || 0,
      comments: p.comments?.summary?.total_count || 0,
      shares: p.shares?.count || 0,
    }));
  } catch (err) {
    fbPosts = [{ error: err.message }];
  }

  // Instagram posts
  let igPosts = [];
  if (IG_USER_ID) {
    try {
      const igResult = await graphGet(`${IG_USER_ID}/media`, {
        fields: "id,caption,timestamp,like_count,comments_count,media_type",
        since,
        limit: 25,
      });
      igPosts = (igResult.data || []).map((p) => ({
        id: p.id,
        caption: (p.caption || "").slice(0, 100),
        timestamp: p.timestamp,
        like_count: p.like_count || 0,
        comments_count: p.comments_count || 0,
        media_type: p.media_type,
      }));
    } catch (err) {
      igPosts = [{ error: err.message }];
    }
  }

  // Aggregate stats
  const fbLikes = fbPosts.reduce((s, p) => s + (p.likes || 0), 0);
  const fbComments = fbPosts.reduce((s, p) => s + (p.comments || 0), 0);
  const igLikes = igPosts.reduce((s, p) => s + (p.like_count || 0), 0);
  const igComments = igPosts.reduce((s, p) => s + (p.comments_count || 0), 0);

  return {
    period_days: lastDays,
    generated_at: new Date().toISOString(),
    facebook: {
      post_count: fbPosts.length,
      total_likes: fbLikes,
      total_comments: fbComments,
      posts: fbPosts,
    },
    instagram: {
      post_count: igPosts.length,
      total_likes: igLikes,
      total_comments: igComments,
      posts: igPosts,
    },
    totals: {
      posts: fbPosts.length + igPosts.length,
      engagement: fbLikes + fbComments + igLikes + igComments,
    },
  };
}

// ── MCP Server Setup ───────────────────────────────────────────────────────────
const server = new Server(
  { name: "meta-social-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "post_to_facebook",
      description:
        "Post a message to the configured Facebook Page. Optionally attach a local image file. Always requires HITL approval before calling — the MetaSocialPoster skill enforces this.",
      inputSchema: {
        type: "object",
        properties: {
          message: {
            type: "string",
            description: "The text content of the Facebook post",
          },
          image_path: {
            type: "string",
            description: "Optional: absolute path to a local image file to attach",
          },
        },
        required: ["message"],
      },
    },
    {
      name: "post_to_instagram",
      description:
        "Post a captioned image to the configured Instagram Business account. Instagram requires an image — a text-only post will return an error with guidance. Always requires HITL approval.",
      inputSchema: {
        type: "object",
        properties: {
          message: {
            type: "string",
            description: "Caption text for the Instagram post (≤2200 chars)",
          },
          image_path: {
            type: "string",
            description: "Absolute path to a local image file (required for Instagram)",
          },
        },
        required: ["message"],
      },
    },
    {
      name: "generate_summary_of_posts",
      description:
        "Fetch Facebook and Instagram post metrics for the last N days. Returns engagement stats (likes, comments, shares) per post and aggregate totals.",
      inputSchema: {
        type: "object",
        properties: {
          last_days: {
            type: "number",
            description: "Number of days to look back (default: 7)",
            default: 7,
          },
        },
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result;
    switch (name) {
      case "post_to_facebook":
        result = await postToFacebook(args.message, args.image_path);
        break;
      case "post_to_instagram":
        result = await postToInstagram(args.message, args.image_path);
        break;
      case "generate_summary_of_posts":
        result = await generateSummaryOfPosts(args.last_days ?? 7);
        break;
      default:
        throw new Error(`Unknown tool: ${name}`);
    }

    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: `Error: ${err.message}` }],
      isError: true,
    };
  }
});

// ── Start Server ───────────────────────────────────────────────────────────────
const transport = new StdioServerTransport();
await server.connect(transport);
console.error(
  `meta-social-mcp server running (DRY_RUN=${DRY_RUN}, PAGE=${PAGE_ID || "not configured"})`
);

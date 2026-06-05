#[macro_use]
extern crate rocket;

use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use comrak::{Options as MarkdownOptions, markdown_to_html};
use rocket::{State, fs::FileServer};
use rocket_dyn_templates::{Template, context};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Row};
use std::{
    collections::{HashMap, HashSet},
    sync::Mutex,
};

const LAW_STATUS: i32 = 10; // siehe bot/utils/modules.py BillIsLaw
const DEFAULT_AUTHOR_LOOKUP_URL: &str = "http://127.0.0.1:8081/discord-user";
const DEFAULT_AUTHOR_LOOKUP_TOKEN: &str = "";

struct AppState {
    db: PgPool,
    author_lookup: DiscordAuthorLookupClient,
}

#[derive(Serialize, Clone)]
struct SearchKey {
    name: &'static str,
    weight: u8,
}

#[derive(Serialize, Clone)]
struct MotionDetail {
    id: i32,
    title: String,
    body: String,
    submitter: i64,
    author: DiscordAuthor,
}

#[derive(Serialize, Clone)]
struct MotionListItem {
    row_id: String,
    id: i32,
    title: String,
    body: String,
    excerpt: String,
    submitter: i64,
    author: DiscordAuthor,
}

#[derive(Serialize, Clone)]
struct BillListItem {
    row_id: String,
    id: i32,
    name: String,
    content: String,
    excerpt: String,
    link: String,
    submitter_description: String,
    submitter: i64,
    author: DiscordAuthor,
    origin_house: String,
    origin_house_label: String,
    type_label: String,
    is_procedure: bool,
    status: i32,
    status_label: String,
    is_law: bool,
    sponsor_count: i64,
}

#[derive(Serialize, Clone)]
struct BillHistoryItem {
    date_label: String,
    note: Option<String>,
    after_status_label: String,
}

#[derive(Serialize, Clone)]
struct BillDetail {
    id: i32,
    name: String,
    content_html: String,
    link: String,
    submitter_description: String,
    origin_house: String,
    origin_house_label: String,
    type_label: String,
    is_procedure: bool,
    is_procedure_label: &'static str,
    status: i32,
    status_label: String,
    is_law: bool,
    submitter: i64,
    author: DiscordAuthor,
    sponsor_count: i64,
    history: Vec<BillHistoryItem>,
    amends: Vec<RelatedBillItem>,
    amended_by: Vec<RelatedBillItem>,
}

#[derive(Serialize, Clone)]
struct RelatedBillItem {
    id: i32,
    name: String,
    href: String,
    kind_label: String,
}

#[derive(Serialize, Clone)]
struct AuthorFilterOption {
    user_id: i64,
    label: String,
}

#[derive(Serialize, Deserialize, Clone)]
struct DiscordAuthor {
    user_id: i64,
    username: String,
    display_name: String,
    avatar_url: String,
}

#[derive(Serialize)]
struct DiscordAuthorLookupRequest {
    user_id: i64,
}

struct DiscordAuthorLookupClient {
    client: reqwest::Client,
    base_url: String,
    bearer_token: String,
    cache: Mutex<HashMap<i64, DiscordAuthor>>,
}

impl DiscordAuthorLookupClient {
    fn from_env() -> Self {
        Self {
            client: reqwest::Client::new(),
            base_url: std::env::var("LEGALCODE_AUTHOR_LOOKUP_URL")
                .unwrap_or_else(|_| DEFAULT_AUTHOR_LOOKUP_URL.to_string()),
            bearer_token: std::env::var("LEGALCODE_AUTHOR_LOOKUP_TOKEN")
                .unwrap_or_else(|_| DEFAULT_AUTHOR_LOOKUP_TOKEN.to_string()),
            cache: Mutex::new(HashMap::new()),
        }
    }

    fn cached(&self, user_id: i64) -> Option<DiscordAuthor> {
        self.cache
            .lock()
            .ok()
            .and_then(|cache| cache.get(&user_id).cloned())
    }

    fn store_cached(&self, author: &DiscordAuthor) {
        if let Ok(mut cache) = self.cache.lock() {
            cache.insert(author.user_id, author.clone());
        }
    }

    async fn lookup(&self, user_id: i64) -> Result<DiscordAuthor, String> {
        if let Some(author) = self.cached(user_id) {
            return Ok(author);
        }

        let response = self
            .client
            .post(&self.base_url)
            .bearer_auth(&self.bearer_token)
            .json(&DiscordAuthorLookupRequest { user_id })
            .send()
            .await
            .map_err(|error| error.to_string())?;

        if !response.status().is_success() {
            return Err(format!(
                "author lookup failed with status {}",
                response.status()
            ));
        }

        let author = response
            .json::<DiscordAuthor>()
            .await
            .map_err(|error| error.to_string())?;

        self.store_cached(&author);
        Ok(author)
    }
}

fn fallback_author(user_id: i64) -> DiscordAuthor {
    DiscordAuthor {
        user_id,
        username: "Unknown User".to_string(),
        display_name: "Unknown User".to_string(),
        avatar_url: "https://cdn.discordapp.com/embed/avatars/0.png".to_string(),
    }
}

async fn resolve_author(lookup: &DiscordAuthorLookupClient, user_id: i64) -> DiscordAuthor {
    lookup
        .lookup(user_id)
        .await
        .unwrap_or_else(|_| fallback_author(user_id))
}

fn detail_href_for_status(id: i32, status: i32) -> String {
    if status == LAW_STATUS {
        format!("/law/{id}")
    } else {
        format!("/bill/{id}")
    }
}

fn detail_kind_label_for_status(status: i32) -> &'static str {
    if status == LAW_STATUS { "Law" } else { "Bill" }
}

fn author_filter_label(author: &DiscordAuthor) -> String {
    format!("{} (@{})", author.display_name, author.username)
}

fn build_author_filter_options(
    authors: impl IntoIterator<Item = DiscordAuthor>,
) -> Vec<AuthorFilterOption> {
    let mut unique = HashMap::<i64, AuthorFilterOption>::new();

    for author in authors {
        unique
            .entry(author.user_id)
            .or_insert_with(|| AuthorFilterOption {
                user_id: author.user_id,
                label: author_filter_label(&author),
            });
    }

    let mut options = unique.into_values().collect::<Vec<_>>();
    options.sort_by(|left, right| {
        left.label
            .to_lowercase()
            .cmp(&right.label.to_lowercase())
            .then_with(|| left.user_id.cmp(&right.user_id))
    });
    options
}

async fn resolve_authors_for_user_ids(
    lookup: &DiscordAuthorLookupClient,
    user_ids: &[i64],
) -> HashMap<i64, DiscordAuthor> {
    let mut authors = HashMap::new();
    let mut seen = HashSet::new();

    for user_id in user_ids {
        if seen.insert(*user_id) {
            authors.insert(*user_id, resolve_author(lookup, *user_id).await);
        }
    }

    authors
}

fn author_for_submitter(authors: &HashMap<i64, DiscordAuthor>, submitter: i64) -> DiscordAuthor {
    authors
        .get(&submitter)
        .cloned()
        .unwrap_or_else(|| fallback_author(submitter))
}

#[derive(Clone, Copy)]
enum RelatedBillDirection {
    Amends,
    AmendedBy,
}

#[derive(Serialize, Clone)]
struct LegalCodeLaw {
    id: i32,
    name: String,
    content_html: String,
    link: String,
}

#[derive(Serialize, Clone)]
struct LegalCodeAmendmentEntry {
    href: String,
    context_label: String,
    law: LegalCodeLaw,
}

#[derive(Serialize, Clone)]
struct LegalCodeJumpLink {
    href: String,
    id: i32,
    name: String,
}

#[derive(Serialize, Clone)]
struct LegalCodeSection {
    anchor_id: String,
    href: String,
    law: LegalCodeLaw,
    amendments: Vec<LegalCodeAmendmentEntry>,
    amends: Vec<LegalCodeJumpLink>,
}

#[derive(Serialize, Clone)]
struct LegalCodeIndexEntry {
    href: String,
    id: i32,
    name: String,
    context_label: Option<String>,
}

#[derive(Serialize, Clone)]
struct LegalCodeIndexSection {
    href: String,
    id: i32,
    name: String,
    amendments: Vec<LegalCodeIndexEntry>,
}

struct LegalCodePageData {
    sections: Vec<LegalCodeSection>,
    index_sections: Vec<LegalCodeIndexSection>,
    total_count: usize,
}

fn law_anchor_id(id: i32) -> String {
    format!("law-{id}")
}

fn law_anchor_href(id: i32) -> String {
    format!("#{}", law_anchor_id(id))
}

fn title_case(value: &str) -> String {
    value
        .split(['_', '-', ' '])
        .filter(|segment| !segment.is_empty())
        .map(|segment| {
            let mut chars = segment.chars();
            match chars.next() {
                Some(first) => {
                    first.to_uppercase().collect::<String>() + &chars.as_str().to_lowercase()
                }
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn display_house_name(house: &str) -> String {
    match house {
        "senate" => "Senate".to_string(),
        "commons" => "Commons".to_string(),
        _ => title_case(house),
    }
}

fn display_bill_status(status: i32) -> &'static str {
    match status {
        0 => "Submitted",
        1 => "Failed in the Legislature", // not in mk13
        2 => "Passed the Legislature",    // not in mk13
        3 => "Vetoed by the Ministry",    // not in mk13
        5 => "Repealed",
        10 => "Active Law",
        20 => "Failed in the Senate",
        21 => "Failed in the Commons",
        22 => "Passed the Senate",
        23 => "Passed the Commons",
        24 => "Awaiting Executive Action",
        25 => "Vetoed by the Executive",
        _ => "Unknown Status",
    }
}

fn display_type_label(origin_house: &str, is_procedure: bool) -> String {
    if is_procedure {
        format!("{} Procedure", display_house_name(origin_house))
    } else {
        "Bill".to_string()
    }
}

fn bool_label(value: bool) -> &'static str {
    if value { "Yes" } else { "No" }
}

fn make_excerpt(text: &str, max_chars: usize) -> String {
    let normalized = text.split_whitespace().collect::<Vec<_>>().join(" ");

    if normalized.chars().count() <= max_chars {
        return normalized;
    }

    let clipped = normalized
        .chars()
        .take(max_chars.saturating_sub(1))
        .collect::<String>()
        .trim_end()
        .to_string();

    format!("{clipped}…")
}

fn pick_markdown_source<'a>(markdown: &'a str, content: &'a str) -> &'a str {
    if markdown.trim().is_empty() {
        content
    } else {
        markdown
    }
}

fn render_bill_markdown(markdown: &str, content: &str) -> String {
    let mut options = MarkdownOptions::default();
    options.extension.strikethrough = true;
    options.extension.table = true;
    options.extension.autolink = true;
    options.extension.tasklist = true;
    options.extension.superscript = true;
    options.parse.smart = true;
    options.render.r#unsafe = false;

    markdown_to_html(pick_markdown_source(markdown, content), &options)
}

fn encode_json_base64<T: Serialize>(value: &T) -> Result<String, String> {
    let bytes = serde_json::to_vec(value).map_err(|error| error.to_string())?;
    Ok(BASE64.encode(bytes))
}

fn motion_search_keys() -> Vec<SearchKey> {
    vec![
        SearchKey {
            name: "title",
            weight: 6,
        },
        SearchKey {
            name: "body",
            weight: 4,
        },
        SearchKey {
            name: "author.display_name",
            weight: 4,
        },
        SearchKey {
            name: "author.username",
            weight: 3,
        },
        SearchKey {
            name: "id",
            weight: 2,
        },
    ]
}

fn bill_search_keys() -> Vec<SearchKey> {
    vec![
        SearchKey {
            name: "name",
            weight: 7,
        },
        SearchKey {
            name: "content",
            weight: 6,
        },
        SearchKey {
            name: "submitter_description",
            weight: 4,
        },
        SearchKey {
            name: "author.display_name",
            weight: 4,
        },
        SearchKey {
            name: "author.username",
            weight: 3,
        },
        SearchKey {
            name: "id",
            weight: 2,
        },
    ]
}

fn bill_status_options() -> Vec<String> {
    [0, 20, 21, 22, 23, 24, 25, 10, 5] // nur mk13 stati
        .into_iter()
        .map(|status| display_bill_status(status).to_string())
        .collect()
}

async fn load_motion_list(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
) -> Result<Vec<MotionListItem>, String> {
    let rows = sqlx::query("SELECT id, title, description, submitter FROM motion ORDER BY id")
        .fetch_all(db)
        .await
        .map_err(|error| error.to_string())?;

    let submitter_ids = rows
        .iter()
        .map(|row| row.try_get("submitter").unwrap_or_default())
        .collect::<Vec<i64>>();
    let authors = resolve_authors_for_user_ids(author_lookup, &submitter_ids).await;

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();
            let title: String = row.try_get("title").unwrap_or_default();
            let body: String = row.try_get("description").unwrap_or_default();
            let submitter: i64 = row.try_get("submitter").unwrap_or_default();

            MotionListItem {
                row_id: format!("motion-{id}"),
                id,
                title,
                excerpt: make_excerpt(&body, 50),
                body,
                submitter,
                author: author_for_submitter(&authors, submitter),
            }
        })
        .collect())
}

async fn load_motion_detail(db: &PgPool, id: i32) -> Result<Option<MotionDetail>, String> {
    let row = sqlx::query("SELECT id, title, description, submitter FROM motion WHERE id = $1")
        .bind(id)
        .fetch_optional(db)
        .await
        .map_err(|error| error.to_string())?;

    let Some(row) = row else {
        return Ok(None);
    };

    let submitter: i64 = row.try_get("submitter").unwrap_or_default();

    Ok(Some(MotionDetail {
        id: row.try_get("id").unwrap_or_default(),
        title: row.try_get("title").unwrap_or_default(),
        body: row.try_get("description").unwrap_or_default(),
        submitter,
        author: fallback_author(submitter),
    }))
}

async fn load_bill_list(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
    laws_only: bool,
) -> Result<Vec<BillListItem>, String> {
    let query = if laws_only {
        "SELECT
            bill.id,
            bill.name,
            bill.content,
            bill.link,
            bill.submitter_description,
            bill.submitter,
            bill.origin_house,
            bill.is_procedure,
            bill.status,
            COUNT(DISTINCT bill_sponsor.sponsor)::bigint AS sponsor_count
        FROM bill
        LEFT JOIN bill_sponsor ON bill_sponsor.bill_id = bill.id
        WHERE bill.status = 10
        GROUP BY bill.id
        ORDER BY bill.id"
    } else {
        "SELECT
            bill.id,
            bill.name,
            bill.content,
            bill.link,
            bill.submitter_description,
            bill.submitter,
            bill.origin_house,
            bill.is_procedure,
            bill.status,
            COUNT(DISTINCT bill_sponsor.sponsor)::bigint AS sponsor_count
        FROM bill
        LEFT JOIN bill_sponsor ON bill_sponsor.bill_id = bill.id
        GROUP BY bill.id
        ORDER BY bill.id"
    };

    let rows = sqlx::query(query)
        .fetch_all(db)
        .await
        .map_err(|error| error.to_string())?;

    let submitter_ids = rows
        .iter()
        .map(|row| row.try_get("submitter").unwrap_or_default())
        .collect::<Vec<i64>>();
    let authors = resolve_authors_for_user_ids(author_lookup, &submitter_ids).await;

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();
            let name: String = row.try_get("name").unwrap_or_default();
            let content: String = row.try_get("content").unwrap_or_default();
            let link: String = row.try_get("link").unwrap_or_default();
            let submitter_description: String =
                row.try_get("submitter_description").unwrap_or_default();
            let submitter: i64 = row.try_get("submitter").unwrap_or_default();
            let origin_house: String = row.try_get("origin_house").unwrap_or_default();
            let origin_house_label = display_house_name(&origin_house);
            let is_procedure: bool = row.try_get("is_procedure").unwrap_or_default();
            let status: i32 = row.try_get("status").unwrap_or_default();
            let type_label = display_type_label(&origin_house, is_procedure);

            BillListItem {
                row_id: format!("bill-{id}"),
                id,
                name,
                excerpt: make_excerpt(&content, 50),
                content,
                link,
                submitter_description,
                submitter,
                author: author_for_submitter(&authors, submitter),
                origin_house,
                origin_house_label: origin_house_label.clone(),
                type_label,
                is_procedure,
                status,
                status_label: display_bill_status(status).to_string(),
                is_law: status == LAW_STATUS,
                sponsor_count: row.try_get("sponsor_count").unwrap_or_default(),
            }
        })
        .collect())
}

async fn load_related_bills(
    db: &PgPool,
    bill_id: i32,
    direction: RelatedBillDirection,
) -> Result<Vec<RelatedBillItem>, String> {
    let query = match direction {
        RelatedBillDirection::Amends => {
            "SELECT related.id, related.name, related.status
            FROM bill_amendment
            JOIN bill AS related ON related.id = bill_amendment.amended_bill_id
            WHERE bill_amendment.amending_bill_id = $1
            ORDER BY related.id"
        }
        RelatedBillDirection::AmendedBy => {
            "SELECT related.id, related.name, related.status
            FROM bill_amendment
            JOIN bill AS related ON related.id = bill_amendment.amending_bill_id
            WHERE bill_amendment.amended_bill_id = $1
            ORDER BY related.id"
        }
    };

    let rows = sqlx::query(query)
        .bind(bill_id)
        .fetch_all(db)
        .await
        .map_err(|error| error.to_string())?;

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();
            let status: i32 = row.try_get("status").unwrap_or_default();

            RelatedBillItem {
                id,
                name: row.try_get("name").unwrap_or_default(),
                href: detail_href_for_status(id, status),
                kind_label: detail_kind_label_for_status(status).to_string(),
            }
        })
        .collect())
}

async fn load_bill_history(db: &PgPool, bill_id: i32) -> Result<Vec<BillHistoryItem>, String> {
    let rows = sqlx::query(
        "SELECT
            COALESCE(TO_CHAR(date, 'YYYY-MM-DD'), 'Unknown date') AS date_label,
            note,
            after_status
        FROM bill_history
        WHERE bill_id = $1
        ORDER BY date DESC NULLS LAST, id DESC",
    )
    .bind(bill_id)
    .fetch_all(db)
    .await
    .map_err(|error| error.to_string())?;

    Ok(rows
        .into_iter()
        .map(|row| {
            let after_status: Option<i32> = row.try_get("after_status").unwrap_or_default();

            BillHistoryItem {
                date_label: row.try_get("date_label").unwrap_or_default(),
                note: row.try_get("note").unwrap_or_default(),
                after_status_label: display_bill_status(after_status.unwrap_or_default())
                    .to_string(),
            }
        })
        .collect())
}

async fn load_bill_detail(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
    id: i32,
    laws_only: bool,
    include_history: bool,
) -> Result<Option<BillDetail>, String> {
    let query = if laws_only {
        "SELECT
            bill.id,
            bill.name,
            bill.content,
            bill.markdown,
            bill.link,
            bill.submitter_description,
            bill.submitter,
            bill.origin_house,
            bill.is_procedure,
            bill.status,
            COUNT(DISTINCT bill_sponsor.sponsor)::bigint AS sponsor_count
        FROM bill
        LEFT JOIN bill_sponsor ON bill_sponsor.bill_id = bill.id
        WHERE bill.id = $1 AND bill.status = 10
        GROUP BY bill.id"
    } else {
        "SELECT
            bill.id,
            bill.name,
            bill.content,
            bill.markdown,
            bill.link,
            bill.submitter_description,
            bill.submitter,
            bill.origin_house,
            bill.is_procedure,
            bill.status,
            COUNT(DISTINCT bill_sponsor.sponsor)::bigint AS sponsor_count
        FROM bill
        LEFT JOIN bill_sponsor ON bill_sponsor.bill_id = bill.id
        WHERE bill.id = $1
        GROUP BY bill.id"
    };

    let row = sqlx::query(query)
        .bind(id)
        .fetch_optional(db)
        .await
        .map_err(|error| error.to_string())?;

    let Some(row) = row else {
        return Ok(None);
    };

    let origin_house: String = row.try_get("origin_house").unwrap_or_default();
    let origin_house_label = display_house_name(&origin_house);
    let is_procedure: bool = row.try_get("is_procedure").unwrap_or_default();
    let status: i32 = row.try_get("status").unwrap_or_default();
    let submitter: i64 = row.try_get("submitter").unwrap_or_default();
    let type_label = display_type_label(&origin_house, is_procedure);

    let history = if include_history {
        load_bill_history(db, id).await?
    } else {
        Vec::new()
    };
    let author = resolve_author(author_lookup, submitter).await;
    let amends = load_related_bills(db, id, RelatedBillDirection::Amends).await?;
    let amended_by = load_related_bills(db, id, RelatedBillDirection::AmendedBy).await?;
    let content: String = row.try_get("content").unwrap_or_default();
    let markdown: String = row.try_get("markdown").unwrap_or_default();

    Ok(Some(BillDetail {
        id: row.try_get("id").unwrap_or_default(),
        name: row.try_get("name").unwrap_or_default(),
        content_html: render_bill_markdown(&markdown, &content),
        link: row.try_get("link").unwrap_or_default(),
        submitter_description: row.try_get("submitter_description").unwrap_or_default(),
        origin_house,
        origin_house_label: origin_house_label.clone(),
        type_label,
        is_procedure,
        is_procedure_label: bool_label(is_procedure),
        status,
        status_label: display_bill_status(status).to_string(),
        is_law: status == LAW_STATUS,
        submitter,
        author,
        sponsor_count: row.try_get("sponsor_count").unwrap_or_default(),
        history,
        amends,
        amended_by,
    }))
}

async fn load_legal_code(db: &PgPool) -> Result<LegalCodePageData, String> {
    let law_rows = sqlx::query(
        "SELECT id, name, content, markdown, link FROM bill WHERE status = $1 ORDER BY id",
    )
    .bind(LAW_STATUS)
    .fetch_all(db)
    .await
    .map_err(|error| error.to_string())?;

    let laws = law_rows
        .into_iter()
        .map(|row| {
            let content: String = row.try_get("content").unwrap_or_default();
            let markdown: String = row.try_get("markdown").unwrap_or_default();

            LegalCodeLaw {
                id: row.try_get("id").unwrap_or_default(),
                name: row.try_get("name").unwrap_or_default(),
                content_html: render_bill_markdown(&markdown, &content),
                link: row.try_get("link").unwrap_or_default(),
            }
        })
        .collect::<Vec<_>>();

    let amendment_rows = sqlx::query(
        "SELECT
            parent.id AS parent_id,
            parent.name AS parent_name,
            child.id,
            child.name,
            child.content,
            child.markdown,
            child.link
        FROM bill_amendment
        JOIN bill AS child ON child.id = bill_amendment.amending_bill_id
        JOIN bill AS parent ON parent.id = bill_amendment.amended_bill_id
        WHERE child.status = $1 AND parent.status = $1
        ORDER BY parent.id, child.id",
    )
    .bind(LAW_STATUS)
    .fetch_all(db)
    .await
    .map_err(|error| error.to_string())?;

    let mut amendments_by_parent = HashMap::<i32, Vec<LegalCodeAmendmentEntry>>::new();
    let mut amends_by_child = HashMap::<i32, Vec<LegalCodeJumpLink>>::new();

    for row in amendment_rows {
        let parent_id: i32 = row.try_get("parent_id").unwrap_or_default();
        let parent_name: String = row.try_get("parent_name").unwrap_or_default();
        let child_id: i32 = row.try_get("id").unwrap_or_default();
        let child_content: String = row.try_get("content").unwrap_or_default();
        let child_markdown: String = row.try_get("markdown").unwrap_or_default();

        amendments_by_parent
            .entry(parent_id)
            .or_default()
            .push(LegalCodeAmendmentEntry {
                href: law_anchor_href(child_id),
                context_label: format!("Amendment to Law #{parent_id}"),
                law: LegalCodeLaw {
                    id: child_id,
                    name: row.try_get("name").unwrap_or_default(),
                    content_html: render_bill_markdown(&child_markdown, &child_content),
                    link: row.try_get("link").unwrap_or_default(),
                },
            });

        amends_by_child
            .entry(child_id)
            .or_default()
            .push(LegalCodeJumpLink {
                href: law_anchor_href(parent_id),
                id: parent_id,
                name: parent_name,
            });
    }

    let mut sections = Vec::with_capacity(laws.len());
    let mut index_sections = Vec::with_capacity(laws.len());

    for law in laws {
        let anchor_id = law_anchor_id(law.id);
        let href = law_anchor_href(law.id);
        let amendments = amendments_by_parent.remove(&law.id).unwrap_or_default();
        let amends = amends_by_child.remove(&law.id).unwrap_or_default();
        let index_amendments = amendments
            .iter()
            .map(|amendment| LegalCodeIndexEntry {
                href: amendment.href.clone(),
                id: amendment.law.id,
                name: amendment.law.name.clone(),
                context_label: Some(amendment.context_label.clone()),
            })
            .collect::<Vec<_>>();

        index_sections.push(LegalCodeIndexSection {
            href: href.clone(),
            id: law.id,
            name: law.name.clone(),
            amendments: index_amendments,
        });

        sections.push(LegalCodeSection {
            anchor_id,
            href,
            law,
            amendments,
            amends,
        });
    }

    Ok(LegalCodePageData {
        total_count: sections.len(),
        sections,
        index_sections,
    })
}

#[get("/")]
async fn index() -> Result<Template, String> {
    Ok(Template::render("index", context! {}))
}

#[get("/motion")]
async fn motion_index(state: &State<AppState>) -> Result<Template, String> {
    let motions = load_motion_list(&state.db, &state.author_lookup).await?;
    let total_count = motions.len();
    let author_options =
        build_author_filter_options(motions.iter().map(|motion| motion.author.clone()));
    let search_items_b64 = encode_json_base64(&motions)?;
    let search_keys_b64 = encode_json_base64(&motion_search_keys())?;

    Ok(Template::render(
        "motions",
        context! {
            motions,
            total_count,
            author_options,
            search_items_b64,
            search_keys_b64,
        },
    ))
}

#[get("/motion/<id>")]
async fn motion(id: i32, state: &State<AppState>) -> Result<Option<Template>, String> {
    let Some(mut motion) = load_motion_detail(&state.db, id).await? else {
        return Ok(None);
    };

    motion.author = resolve_author(&state.author_lookup, motion.submitter).await;

    Ok(Some(Template::render(
        "motion",
        context! {
            motion,
        },
    )))
}

#[get("/bill")]
async fn bill_index(state: &State<AppState>) -> Result<Template, String> {
    let bills = load_bill_list(&state.db, &state.author_lookup, false).await?;
    let total_count = bills.len();
    let author_options = build_author_filter_options(bills.iter().map(|bill| bill.author.clone()));
    let status_options = bill_status_options();
    let search_items_b64 = encode_json_base64(&bills)?;
    let search_keys_b64 = encode_json_base64(&bill_search_keys())?;

    Ok(Template::render(
        "bills",
        context! {
            bills,
            total_count,
            status_options,
            author_options,
            search_items_b64,
            search_keys_b64,
        },
    ))
}

#[get("/bill/<id>")]
async fn bill(id: i32, state: &State<AppState>) -> Result<Option<Template>, String> {
    let Some(bill) = load_bill_detail(&state.db, &state.author_lookup, id, false, true).await?
    else {
        return Ok(None);
    };

    Ok(Some(Template::render(
        "bill",
        context! {
            bill,
        },
    )))
}

#[get("/law")]
async fn law_index(state: &State<AppState>) -> Result<Template, String> {
    let laws = load_bill_list(&state.db, &state.author_lookup, true).await?;
    let total_count = laws.len();
    let author_options = build_author_filter_options(laws.iter().map(|law| law.author.clone()));
    let search_items_b64 = encode_json_base64(&laws)?;
    let search_keys_b64 = encode_json_base64(&bill_search_keys())?;

    Ok(Template::render(
        "laws",
        context! {
            laws,
            total_count,
            author_options,
            search_items_b64,
            search_keys_b64,
        },
    ))
}

#[get("/law/<id>")]
async fn law(id: i32, state: &State<AppState>) -> Result<Option<Template>, String> {
    let Some(law) = load_bill_detail(&state.db, &state.author_lookup, id, true, false).await?
    else {
        return Ok(None);
    };

    Ok(Some(Template::render(
        "law",
        context! {
            law,
        },
    )))
}

#[get("/legal-code")]
async fn legal_code(state: &State<AppState>) -> Result<Template, String> {
    let legal_code = load_legal_code(&state.db).await?;
    let total_count = legal_code.total_count;
    let sections = legal_code.sections;
    let index_sections = legal_code.index_sections;

    Ok(Template::render(
        "legal_code",
        context! {
            sections,
            index_sections,
            total_count,
        },
    ))
}

#[catch(404)]
fn not_found() -> Template {
    Template::render("404", context! {})
}

#[launch]
async fn rocket() -> _ {
    let database_url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    let author_lookup = DiscordAuthorLookupClient::from_env();

    let pool = PgPool::connect(&database_url)
        .await
        .expect("failed to connect to PostgreSQL");

    rocket::build()
        .manage(AppState {
            db: pool,
            author_lookup,
        })
        .mount(
            "/",
            routes![
                index,
                motion_index,
                motion,
                bill_index,
                bill,
                law_index,
                law,
                legal_code
            ],
        )
        .attach(Template::fairing())
        .mount("/static", FileServer::from("static"))
        .register("/", catchers![not_found])
}

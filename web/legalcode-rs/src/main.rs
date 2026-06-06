#[macro_use]
extern crate rocket;

use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use comrak::{Options as MarkdownOptions, markdown_to_html};
use percent_encoding::{AsciiSet, CONTROLS, utf8_percent_encode};
use regex::{Captures, Regex};
use rocket::{State, fs::FileServer, http::ContentType};
use rocket_dyn_templates::{Template, context};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Row};
use std::{
    collections::{HashMap, HashSet},
    io::Cursor,
    path::{Component, PathBuf},
    sync::{Mutex, OnceLock},
};
use zip::ZipArchive;

const LAW_STATUS: i32 = 10; // siehe bot/utils/modules.py BillIsLaw
const AWAITING_EXECUTIVE_STATUS: i32 = 24; // siehe bot/utils/models.py BillAwaitingExecutive
const DEFAULT_AUTHOR_LOOKUP_URL: &str = "http://127.0.0.1:8081/discord-user";
const DEFAULT_AUTHOR_LOOKUP_TOKEN: &str = "";
const GDOC_FONT_SIZE_SCALE: f32 = 1.1;
const ASSET_PATH_ENCODE_SET: &AsciiSet = &CONTROLS
    .add(b' ')
    .add(b'"')
    .add(b'#')
    .add(b'%')
    .add(b'<')
    .add(b'>')
    .add(b'?')
    .add(b'[')
    .add(b'\\')
    .add(b']')
    .add(b'^')
    .add(b'`')
    .add(b'{')
    .add(b'|')
    .add(b'}');

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
struct DashboardLawItem {
    id: i32,
    name: String,
    href: String,
    passed_date_label: Option<String>,
}

#[derive(Serialize, Clone)]
struct DashboardSessionBillItem {
    id: i32,
    name: String,
    href: String,
    author: DiscordAuthor,
}

#[derive(Serialize, Clone)]
struct DashboardSessionMotionItem {
    id: i32,
    title: String,
    href: String,
    author: DiscordAuthor,
}

#[derive(Serialize, Clone)]
struct DashboardSession {
    id: i32,
    display_name: String,
    session_kind_label: String,
    status_label: String,
    vote_form: Option<String>,
    presider_label: &'static str,
    presider: DiscordAuthor,
    tab_id: String,
    panel_id: String,
    bills: Vec<DashboardSessionBillItem>,
    motions: Vec<DashboardSessionMotionItem>,
}

#[derive(Serialize, Clone)]
struct DashboardChamber {
    key: &'static str,
    title: &'static str,
    empty_message: &'static str,
    has_sessions: bool,
    has_tabs: bool,
    sessions: Vec<DashboardSession>,
}

#[derive(Serialize, Clone)]
struct DashboardExecutiveBillItem {
    id: i32,
    name: String,
    href: String,
    author: DiscordAuthor,
    executive_deadline_label: String,
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
    content_class: &'static str,
    uses_gdoc_html: bool,
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
    content_class: &'static str,
    uses_gdoc_html: bool,
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
    has_gdoc_html: bool,
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

struct RenderedDocumentContent {
    html: String,
    css_class: &'static str,
    uses_gdoc_html: bool,
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

fn body_re() -> &'static Regex {
    static BODY_RE: OnceLock<Regex> = OnceLock::new();
    BODY_RE.get_or_init(|| Regex::new(r"(?is)<body([^>]*)>(.*)</body>").unwrap())
}

fn style_tag_re() -> &'static Regex {
    static STYLE_TAG_RE: OnceLock<Regex> = OnceLock::new();
    STYLE_TAG_RE.get_or_init(|| Regex::new(r"(?is)<style[^>]*>(.*?)</style>").unwrap())
}

fn style_attr_re() -> &'static Regex {
    static STYLE_ATTR_RE: OnceLock<Regex> = OnceLock::new();
    STYLE_ATTR_RE.get_or_init(|| Regex::new(r#"(?is)\bstyle\s*=\s*(?:"[^"]*"|'[^']*')"#).unwrap())
}

fn class_attr_re() -> &'static Regex {
    static CLASS_ATTR_RE: OnceLock<Regex> = OnceLock::new();
    CLASS_ATTR_RE.get_or_init(|| Regex::new(r#"(?i)\bclass\s*=\s*(?:"[^"]*"|'[^']*')"#).unwrap())
}

fn src_attr_re() -> &'static Regex {
    static SRC_ATTR_RE: OnceLock<Regex> = OnceLock::new();
    SRC_ATTR_RE.get_or_init(|| Regex::new(r#"(?is)\bsrc\s*=\s*(?:"[^"]*"|'[^']*')"#).unwrap())
}

fn css_url_re() -> &'static Regex {
    static CSS_URL_RE: OnceLock<Regex> = OnceLock::new();
    CSS_URL_RE.get_or_init(|| Regex::new(r#"(?is)url\(\s*([^)]*?)\s*\)"#).unwrap())
}

fn font_size_value_re() -> &'static Regex {
    static FONT_SIZE_VALUE_RE: OnceLock<Regex> = OnceLock::new();
    FONT_SIZE_VALUE_RE
        .get_or_init(|| Regex::new(r"(?i)^\s*(-?\d*\.?\d+)\s*(pt|px|em|rem|%)\s*$").unwrap())
}

fn important_suffix_re() -> &'static Regex {
    static IMPORTANT_SUFFIX_RE: OnceLock<Regex> = OnceLock::new();
    IMPORTANT_SUFFIX_RE.get_or_init(|| Regex::new(r"(?i)\s*!important\s*$").unwrap())
}

fn rgb_function_re() -> &'static Regex {
    static RGB_FUNCTION_RE: OnceLock<Regex> = OnceLock::new();
    RGB_FUNCTION_RE.get_or_init(|| Regex::new(r"(?i)^rgba?\((.*)\)$").unwrap())
}

fn hsl_function_re() -> &'static Regex {
    static HSL_FUNCTION_RE: OnceLock<Regex> = OnceLock::new();
    HSL_FUNCTION_RE.get_or_init(|| Regex::new(r"(?i)^hsla?\((.*)\)$").unwrap())
}

fn event_attr_re() -> &'static Regex {
    static EVENT_ATTR_RE: OnceLock<Regex> = OnceLock::new();
    EVENT_ATTR_RE.get_or_init(|| {
        Regex::new(r#"(?is)\s+on[a-z0-9:_-]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)"#).unwrap()
    })
}

fn dangerous_block_re() -> &'static Regex {
    static DANGEROUS_BLOCK_RE: OnceLock<Regex> = OnceLock::new();
    DANGEROUS_BLOCK_RE.get_or_init(|| {
        Regex::new(
            r"(?is)<(?:script|iframe|object|embed|frame|frameset)[^>]*>.*?</(?:script|iframe|object|embed|frame|frameset)\s*>",
        )
        .unwrap()
    })
}

fn dangerous_single_re() -> &'static Regex {
    static DANGEROUS_SINGLE_RE: OnceLock<Regex> = OnceLock::new();
    DANGEROUS_SINGLE_RE.get_or_init(|| {
        Regex::new(r"(?is)<(?:script|iframe|object|embed|frame|frameset|meta|link|base)[^>]*?/?>")
            .unwrap()
    })
}

fn css_comment_re() -> &'static Regex {
    static CSS_COMMENT_RE: OnceLock<Regex> = OnceLock::new();
    CSS_COMMENT_RE.get_or_init(|| Regex::new(r"(?s)/\*.*?\*/").unwrap())
}

fn quoted_attr_info(attribute: &str) -> Option<(char, &str)> {
    let (_, raw_value) = attribute.split_once('=')?;
    let trimmed = raw_value.trim();

    if trimmed.len() < 2 {
        return None;
    }

    let quote = trimmed.chars().next()?;
    if quote != '"' && quote != '\'' {
        return None;
    }

    Some((quote, trimmed.strip_prefix(quote)?.strip_suffix(quote)?))
}

fn quoted_attr_value(attribute: &str) -> Option<&str> {
    quoted_attr_info(attribute).map(|(_, value)| value)
}

fn body_classes(body_attributes: &str) -> Vec<String> {
    let Some(class_attribute) = class_attr_re().find(body_attributes) else {
        return Vec::new();
    };

    quoted_attr_value(class_attribute.as_str())
        .unwrap_or_default()
        .split_whitespace()
        .filter(|class_name| {
            !class_name.is_empty()
                && class_name.chars().all(|character| {
                    character.is_ascii_alphanumeric() || character == '-' || character == '_'
                })
        })
        .map(ToString::to_string)
        .collect()
}

fn encode_asset_path(path: &str) -> String {
    path.split('/')
        .map(|segment| utf8_percent_encode(segment, ASSET_PATH_ENCODE_SET).to_string())
        .collect::<Vec<_>>()
        .join("/")
}

fn asset_route_href(id: i32, path: &str) -> String {
    format!("/_bill-asset/{id}/{}", encode_asset_path(path))
}

fn normalize_zip_path(path: &str) -> Option<String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return None;
    }

    let without_fragment = trimmed.split(['#', '?']).next().unwrap_or_default();
    let normalized = without_fragment.replace('\\', "/");
    let mut cleaned = Vec::new();

    for segment in normalized.split('/') {
        match segment {
            "" | "." => continue,
            ".." => return None,
            value => cleaned.push(value),
        }
    }

    if cleaned.is_empty() {
        None
    } else {
        Some(cleaned.join("/"))
    }
}

fn relative_asset_path(reference: &str) -> Option<String> {
    let trimmed = reference.trim();
    if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with('/') {
        return None;
    }

    let lowered = trimmed.to_ascii_lowercase();
    if lowered.starts_with("http://")
        || lowered.starts_with("https://")
        || lowered.starts_with("data:")
        || lowered.starts_with("mailto:")
        || lowered.starts_with("tel:")
        || lowered.starts_with("javascript:")
        || lowered.starts_with("blob:")
        || lowered.starts_with("about:")
    {
        return None;
    }

    normalize_zip_path(trimmed)
}

fn rewrite_css_urls(input: &str, bill_id: i32) -> String {
    css_url_re()
        .replace_all(input, |captures: &Captures| {
            let Some(raw_reference) = captures.get(1) else {
                return captures[0].to_string();
            };

            let reference = raw_reference.as_str().trim().trim_matches(['"', '\'']);
            match relative_asset_path(reference) {
                Some(path) => format!("url(\"{}\")", asset_route_href(bill_id, &path)),
                None => captures[0].to_string(),
            }
        })
        .into_owned()
}

fn format_scaled_css_number(value: f32) -> String {
    let rounded = (value * 100.0).round() / 100.0;
    let mut formatted = format!("{rounded:.2}");

    while formatted.contains('.') && formatted.ends_with('0') {
        formatted.pop();
    }

    if formatted.ends_with('.') {
        formatted.pop();
    }

    formatted
}

fn decode_html_attribute_value(value: &str) -> String {
    value
        .replace("&quot;", "\"")
        .replace("&#34;", "\"")
        .replace("&apos;", "'")
        .replace("&#39;", "'")
        .replace("&amp;", "&")
}

fn encode_html_attribute_value(value: &str, quote: char) -> String {
    let mut escaped = value.replace('&', "&amp;");

    match quote {
        '"' => escaped = escaped.replace('"', "&quot;"),
        '\'' => escaped = escaped.replace('\'', "&#39;"),
        _ => {}
    }

    escaped
}

fn split_css_declarations(input: &str) -> Vec<String> {
    let mut declarations = Vec::new();
    let mut current = String::new();
    let mut quote: Option<char> = None;
    let mut escaped = false;
    let mut paren_depth: usize = 0;

    for character in input.chars() {
        if let Some(current_quote) = quote {
            current.push(character);

            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == current_quote {
                quote = None;
            }

            continue;
        }

        match character {
            '"' | '\'' => {
                quote = Some(character);
                current.push(character);
            }
            '(' => {
                paren_depth += 1;
                current.push(character);
            }
            ')' => {
                paren_depth = paren_depth.saturating_sub(1);
                current.push(character);
            }
            ';' if paren_depth == 0 => {
                if !current.trim().is_empty() {
                    declarations.push(current.trim().to_string());
                }
                current.clear();
            }
            _ => current.push(character),
        }
    }

    if !current.trim().is_empty() {
        declarations.push(current.trim().to_string());
    }

    declarations
}

fn split_css_function_args(input: &str) -> Vec<String> {
    let sanitized = input.replace('/', " / ");

    if sanitized.contains(',') {
        sanitized
            .split(',')
            .map(str::trim)
            .filter(|part| !part.is_empty() && *part != "/")
            .map(ToString::to_string)
            .collect()
    } else {
        sanitized
            .split_whitespace()
            .filter(|part| !part.is_empty() && *part != "/")
            .map(ToString::to_string)
            .collect()
    }
}

fn strip_important_suffix(value: &str) -> (String, bool) {
    let trimmed = value.trim();

    if let Some(match_) = important_suffix_re().find(trimmed) {
        return (trimmed[..match_.start()].trim_end().to_string(), true);
    }

    (trimmed.to_string(), false)
}

fn scale_font_size_value(value: &str) -> String {
    let (core_value, is_important) = strip_important_suffix(value);
    let Some(captures) = font_size_value_re().captures(&core_value) else {
        return value.trim().to_string();
    };

    let raw_value = captures
        .get(1)
        .map(|match_| match_.as_str())
        .unwrap_or_default();
    let unit = captures
        .get(2)
        .map(|match_| match_.as_str())
        .unwrap_or_default();

    let scaled = raw_value
        .parse::<f32>()
        .map(|parsed| format_scaled_css_number(parsed * GDOC_FONT_SIZE_SCALE))
        .unwrap_or_else(|_| raw_value.to_string());

    if is_important {
        format!("{scaled}{unit} !important")
    } else {
        format!("{scaled}{unit}")
    }
}

fn wrap_font_family_value(value: &str) -> String {
    let (core_value, is_important) = strip_important_suffix(value);
    let trimmed = core_value.trim();

    if trimmed.is_empty() || trimmed.contains("--gdoc-font-family-override") {
        return value.trim().to_string();
    }

    let wrapped = format!("var(--gdoc-font-family-override, {trimmed})");

    if is_important {
        format!("{wrapped} !important")
    } else {
        wrapped
    }
}

fn parse_alpha_component(value: &str) -> Option<f32> {
    let trimmed = value.trim();

    if let Some(percent) = trimmed.strip_suffix('%') {
        return percent
            .trim()
            .parse::<f32>()
            .ok()
            .map(|alpha| alpha / 100.0);
    }

    trimmed.parse::<f32>().ok()
}

fn parse_rgb_component(value: &str) -> Option<u8> {
    let trimmed = value.trim();

    let parsed = if let Some(percent) = trimmed.strip_suffix('%') {
        percent
            .trim()
            .parse::<f32>()
            .ok()
            .map(|component| (component * 255.0) / 100.0)?
    } else {
        trimmed.parse::<f32>().ok()?
    };

    Some(parsed.clamp(0.0, 255.0).round() as u8)
}

fn parse_percentage(value: &str) -> Option<f32> {
    value.trim().strip_suffix('%')?.trim().parse::<f32>().ok()
}

fn parse_hex_color(value: &str) -> Option<(u8, u8, u8, Option<f32>)> {
    let hex = value.strip_prefix('#')?;

    fn parse_pair(value: &str) -> Option<u8> {
        u8::from_str_radix(value, 16).ok()
    }

    fn expand_single(value: char) -> Option<u8> {
        let nibble = value.to_digit(16)? as u8;
        Some((nibble << 4) | nibble)
    }

    match hex.len() {
        3 => Some((
            expand_single(hex.chars().nth(0)?)?,
            expand_single(hex.chars().nth(1)?)?,
            expand_single(hex.chars().nth(2)?)?,
            None,
        )),
        4 => Some((
            expand_single(hex.chars().nth(0)?)?,
            expand_single(hex.chars().nth(1)?)?,
            expand_single(hex.chars().nth(2)?)?,
            Some(expand_single(hex.chars().nth(3)?)? as f32 / 255.0),
        )),
        6 => Some((
            parse_pair(&hex[0..2])?,
            parse_pair(&hex[2..4])?,
            parse_pair(&hex[4..6])?,
            None,
        )),
        8 => Some((
            parse_pair(&hex[0..2])?,
            parse_pair(&hex[2..4])?,
            parse_pair(&hex[4..6])?,
            Some(parse_pair(&hex[6..8])? as f32 / 255.0),
        )),
        _ => None,
    }
}

fn parse_rgb_color(value: &str) -> Option<(u8, u8, u8, Option<f32>)> {
    let captures = rgb_function_re().captures(value.trim())?;
    let arguments = captures.get(1)?.as_str();
    let parts = split_css_function_args(arguments);

    if parts.len() < 3 {
        return None;
    }

    let red = parse_rgb_component(&parts[0])?;
    let green = parse_rgb_component(&parts[1])?;
    let blue = parse_rgb_component(&parts[2])?;
    let alpha = parts
        .get(3)
        .and_then(|component| parse_alpha_component(component));

    Some((red, green, blue, alpha))
}

fn parse_hsl_color(value: &str) -> Option<(f32, Option<f32>)> {
    let captures = hsl_function_re().captures(value.trim())?;
    let arguments = captures.get(1)?.as_str();
    let parts = split_css_function_args(arguments);

    if parts.len() < 3 {
        return None;
    }

    let saturation = parse_percentage(&parts[1])?;
    let alpha = parts
        .get(3)
        .and_then(|component| parse_alpha_component(component));

    Some((saturation, alpha))
}

fn is_neutral_rgb(red: u8, green: u8, blue: u8) -> bool {
    let highest = red.max(green).max(blue);
    let lowest = red.min(green).min(blue);

    highest.saturating_sub(lowest) <= 12
}

fn is_neutral_named_color(value: &str) -> bool {
    matches!(
        value,
        "black"
            | "gray"
            | "grey"
            | "silver"
            | "dimgray"
            | "dimgrey"
            | "darkgray"
            | "darkgrey"
            | "lightgray"
            | "lightgrey"
            | "gainsboro"
            | "whitesmoke"
            | "white"
    )
}

fn is_neutral_text_color(value: &str) -> bool {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return false;
    }

    let lowered = trimmed.to_ascii_lowercase();
    if lowered.starts_with("var(")
        || lowered == "inherit"
        || lowered == "currentcolor"
        || lowered == "transparent"
        || lowered == "unset"
        || lowered == "initial"
        || lowered == "revert"
    {
        return false;
    }

    if is_neutral_named_color(&lowered) {
        return true;
    }

    if trimmed == "#0c343d" {
        return false;
    }

    if let Some((red, green, blue, alpha)) = parse_hex_color(trimmed) {
        return alpha.unwrap_or(1.0) > 0.0 && is_neutral_rgb(red, green, blue);
    }

    if let Some((red, green, blue, alpha)) = parse_rgb_color(trimmed) {
        return alpha.unwrap_or(1.0) > 0.0 && is_neutral_rgb(red, green, blue);
    }

    if let Some((saturation, alpha)) = parse_hsl_color(trimmed) {
        return alpha.unwrap_or(1.0) > 0.0 && saturation <= 5.0;
    }

    false
}

fn normalize_text_color_value(value: &str) -> String {
    let (core_value, is_important) = strip_important_suffix(value);

    if !is_neutral_text_color(&core_value) {
        return value.trim().to_string();
    }

    if is_important {
        "var(--gdoc-neutral-text-color) !important".to_string()
    } else {
        "var(--gdoc-neutral-text-color)".to_string()
    }
}

fn normalize_css_declaration_list(input: &str) -> String {
    split_css_declarations(input)
        .into_iter()
        .filter_map(|declaration| {
            let Some((property, value)) = declaration.split_once(':') else {
                return Some(declaration.trim().to_string());
            };

            let property_name = property.trim();
            let property_key = property_name.to_ascii_lowercase();
            let value_text = value.trim();

            let normalized_value = match property_key.as_str() {
                "font-size" => scale_font_size_value(value_text),
                "font-family" => wrap_font_family_value(value_text),
                "color" | "-webkit-text-fill-color" => normalize_text_color_value(value_text),
                _ => value_text.to_string(),
            };

            Some(format!("{property_name}:{normalized_value}"))
        })
        .collect::<Vec<_>>()
        .join(";")
}

fn normalize_html_style_attributes(input: &str) -> String {
    style_attr_re()
        .replace_all(input, |captures: &Captures| {
            let attribute = captures
                .get(0)
                .map(|match_| match_.as_str())
                .unwrap_or_default();
            let Some((quote, raw_value)) = quoted_attr_info(attribute) else {
                return attribute.to_string();
            };

            let decoded = decode_html_attribute_value(raw_value);
            let normalized = normalize_css_declaration_list(&decoded);

            if normalized.trim().is_empty() {
                String::new()
            } else {
                let escaped = encode_html_attribute_value(&normalized, quote);
                format!("style={quote}{escaped}{quote}")
            }
        })
        .into_owned()
}

fn rewrite_html_asset_references(input: &str, bill_id: i32) -> String {
    let with_src_rewritten = src_attr_re()
        .replace_all(input, |captures: &Captures| {
            let attribute = captures
                .get(0)
                .map(|match_| match_.as_str())
                .unwrap_or_default();
            let Some(reference) = quoted_attr_value(attribute) else {
                return attribute.to_string();
            };

            match relative_asset_path(reference) {
                Some(path) => format!("src=\"{}\"", asset_route_href(bill_id, &path)),
                None => attribute.to_string(),
            }
        })
        .into_owned();

    rewrite_css_urls(&with_src_rewritten, bill_id)
}

fn sanitize_google_doc_body_html(input: &str) -> String {
    let without_dangerous_blocks = dangerous_block_re().replace_all(input, "");
    let without_dangerous_tags = dangerous_single_re().replace_all(&without_dangerous_blocks, "");
    event_attr_re()
        .replace_all(&without_dangerous_tags, "")
        .into_owned()
}

fn split_selector_list(selector_list: &str) -> Vec<String> {
    let mut selectors = Vec::new();
    let mut current = String::new();
    let mut paren_depth: usize = 0;
    let mut bracket_depth: usize = 0;

    for character in selector_list.chars() {
        match character {
            '(' => {
                paren_depth += 1;
                current.push(character);
            }
            ')' => {
                paren_depth = paren_depth.saturating_sub(1);
                current.push(character);
            }
            '[' => {
                bracket_depth += 1;
                current.push(character);
            }
            ']' => {
                bracket_depth = bracket_depth.saturating_sub(1);
                current.push(character);
            }
            ',' if paren_depth == 0 && bracket_depth == 0 => {
                selectors.push(current.trim().to_string());
                current.clear();
            }
            _ => current.push(character),
        }
    }

    if !current.trim().is_empty() {
        selectors.push(current.trim().to_string());
    }

    selectors
}

fn scope_selector(selector: &str, scope: &str) -> Option<String> {
    let trimmed = selector.trim();
    if trimmed.is_empty() {
        return None;
    }

    if trimmed.starts_with('@') {
        return Some(trimmed.to_string());
    }

    let scoped =
        if trimmed.contains("body") || trimmed.contains("html") || trimmed.contains(":root") {
            trimmed
                .replace(":root", scope)
                .replace("body", scope)
                .replace("html", scope)
        } else {
            format!("{scope} {trimmed}")
        };

    Some(scoped)
}

fn scope_css_block(css: &str, scope: &str) -> String {
    let mut output = String::new();
    let mut selector_buffer = String::new();
    let mut characters = css.chars();

    while let Some(character) = characters.next() {
        if character != '{' {
            selector_buffer.push(character);
            continue;
        }

        let selector = selector_buffer.trim().to_string();
        selector_buffer.clear();

        let mut block = String::new();
        let mut depth = 1usize;
        let mut quote: Option<char> = None;
        let mut escaped = false;

        for block_character in characters.by_ref() {
            if let Some(current_quote) = quote {
                block.push(block_character);
                if escaped {
                    escaped = false;
                } else if block_character == '\\' {
                    escaped = true;
                } else if block_character == current_quote {
                    quote = None;
                }
                continue;
            }

            match block_character {
                '"' | '\'' => {
                    quote = Some(block_character);
                    block.push(block_character);
                }
                '{' => {
                    depth += 1;
                    block.push(block_character);
                }
                '}' => {
                    depth = depth.saturating_sub(1);
                    if depth == 0 {
                        break;
                    }
                    block.push(block_character);
                }
                _ => block.push(block_character),
            }
        }

        if selector.starts_with('@') {
            if selector.starts_with("@media") || selector.starts_with("@supports") {
                output.push_str(&selector);
                output.push('{');
                output.push_str(&scope_css_block(&block, scope));
                output.push('}');
            } else if !selector.starts_with("@page") {
                output.push_str(&selector);
                output.push('{');
                output.push_str(&block);
                output.push('}');
            }
            continue;
        }

        let scoped_selectors = split_selector_list(&selector)
            .into_iter()
            .filter_map(|entry| scope_selector(&entry, scope))
            .collect::<Vec<_>>();

        if scoped_selectors.is_empty() {
            continue;
        }

        let normalized_block = normalize_css_declaration_list(&block);

        output.push_str(&scoped_selectors.join(", "));
        output.push('{');
        output.push_str(&normalized_block);
        output.push('}');
    }

    output
}

fn extract_google_doc_styles(document_html: &str) -> Vec<String> {
    style_tag_re()
        .captures_iter(document_html)
        .filter_map(|captures| captures.get(1).map(|value| value.as_str().to_string()))
        .collect()
}

fn extract_google_doc_body(document_html: &str) -> (String, String) {
    if let Some(captures) = body_re().captures(document_html) {
        let attributes = captures
            .get(1)
            .map(|value| value.as_str().to_string())
            .unwrap_or_default();
        let body_html = captures
            .get(2)
            .map(|value| value.as_str().to_string())
            .unwrap_or_default();

        return (attributes, body_html);
    }

    (String::new(), document_html.to_string())
}

fn render_google_doc_html(document_id: i32, document_html: &str) -> Option<String> {
    let styles = extract_google_doc_styles(document_html);
    let (body_attributes, body_html) = extract_google_doc_body(document_html);
    let body_without_style_tags = style_tag_re().replace_all(&body_html, "").into_owned();
    let rewritten_body = rewrite_html_asset_references(&body_without_style_tags, document_id);
    let normalized_body = normalize_html_style_attributes(&rewritten_body);
    let sanitized_body = sanitize_google_doc_body_html(&normalized_body);

    if sanitized_body.trim().is_empty() {
        return None;
    }

    let scope_id = format!("gdoc-doc-{document_id}");
    let scope_selector = format!("#{scope_id}");
    let wrapper_classes = body_classes(&body_attributes);
    let mut class_names = vec!["gdoc-rendered".to_string()];
    class_names.extend(wrapper_classes);

    let scoped_styles = styles
        .into_iter()
        .map(|stylesheet| rewrite_css_urls(&stylesheet, document_id))
        .map(|stylesheet| css_comment_re().replace_all(&stylesheet, "").into_owned())
        .map(|stylesheet| scope_css_block(&stylesheet, &scope_selector))
        .filter(|stylesheet| !stylesheet.trim().is_empty())
        .collect::<Vec<_>>()
        .join("\n");

    let mut rendered = String::new();

    if !scoped_styles.trim().is_empty() {
        rendered.push_str("<style>");
        rendered.push_str(&scoped_styles);
        rendered.push_str("</style>");
    }

    rendered.push_str(&format!(
        "<div id=\"{scope_id}\" class=\"{}\">{}</div>",
        class_names.join(" "),
        sanitized_body
    ));

    Some(rendered)
}

fn render_bill_content(
    bill_id: i32,
    html: &str,
    markdown: &str,
    content: &str,
) -> RenderedDocumentContent {
    if let Some(rendered_html) = (!html.trim().is_empty())
        .then(|| render_google_doc_html(bill_id, html))
        .flatten()
    {
        return RenderedDocumentContent {
            html: rendered_html,
            css_class: "content-rendered content-gdoc-host",
            uses_gdoc_html: true,
        };
    }

    RenderedDocumentContent {
        html: render_bill_markdown(markdown, content),
        css_class: "content-rendered content-markdown",
        uses_gdoc_html: false,
    }
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

fn display_session_name(house_name: &str, session_kind: &str, display_id: i32) -> String {
    let kind = if session_kind == "Emergency" {
        " Emergency"
    } else {
        ""
    };

    format!("{house_name}{kind} Session #{display_id}")
}

async fn load_recent_dashboard_laws(db: &PgPool) -> Result<Vec<DashboardLawItem>, String> {
    let rows = sqlx::query(
        "SELECT
            bill.id,
            bill.name,
            CASE
                WHEN MAX(bill_history.date) FILTER (WHERE bill_history.after_status = $1) IS NULL
                    THEN NULL
                ELSE TO_CHAR(
                    MAX(bill_history.date) FILTER (WHERE bill_history.after_status = $1),
                    'YYYY-MM-DD HH24:MI'
                ) || ' UTC'
            END AS passed_date_label
        FROM bill
        LEFT JOIN bill_history ON bill_history.bill_id = bill.id
        WHERE bill.status = $1
        GROUP BY bill.id
        ORDER BY
            MAX(bill_history.date) FILTER (WHERE bill_history.after_status = $1) DESC NULLS LAST,
            bill.id DESC
        LIMIT 3",
    )
    .bind(LAW_STATUS)
    .fetch_all(db)
    .await
    .map_err(|error| error.to_string())?;

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();

            DashboardLawItem {
                id,
                name: row.try_get("name").unwrap_or_default(),
                href: format!("/law/{id}"),
                passed_date_label: row.try_get("passed_date_label").unwrap_or_default(),
            }
        })
        .collect())
}

async fn load_dashboard_session_bills(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
    session_id: i32,
) -> Result<Vec<DashboardSessionBillItem>, String> {
    let mut rows = sqlx::query(
        "SELECT
            bill.id,
            bill.name,
            bill.submitter,
            bill.status
        FROM bill_session
        JOIN bill ON bill.id = bill_session.bill_id
        WHERE bill_session.leg_session = $1
        ORDER BY bill.id",
    )
    .bind(session_id)
    .fetch_all(db)
    .await
    .map_err(|error| error.to_string())?;

    if rows.is_empty() {
        rows = sqlx::query(
            "SELECT id, name, submitter, status
            FROM bill
            WHERE leg_session = $1
            ORDER BY id",
        )
        .bind(session_id)
        .fetch_all(db)
        .await
        .map_err(|error| error.to_string())?;
    }

    let submitter_ids = rows
        .iter()
        .map(|row| row.try_get("submitter").unwrap_or_default())
        .collect::<Vec<i64>>();
    let authors = resolve_authors_for_user_ids(author_lookup, &submitter_ids).await;

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();
            let submitter: i64 = row.try_get("submitter").unwrap_or_default();
            let status: i32 = row.try_get("status").unwrap_or_default();

            DashboardSessionBillItem {
                id,
                name: row.try_get("name").unwrap_or_default(),
                href: detail_href_for_status(id, status),
                author: author_for_submitter(&authors, submitter),
            }
        })
        .collect())
}

async fn load_dashboard_session_motions(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
    session_id: i32,
) -> Result<Vec<DashboardSessionMotionItem>, String> {
    let rows = sqlx::query(
        "SELECT id, title, submitter
        FROM motion
        WHERE leg_session = $1
        ORDER BY id",
    )
    .bind(session_id)
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
            let submitter: i64 = row.try_get("submitter").unwrap_or_default();

            DashboardSessionMotionItem {
                id,
                title: row.try_get("title").unwrap_or_default(),
                href: format!("/motion/{id}"),
                author: author_for_submitter(&authors, submitter),
            }
        })
        .collect())
}

async fn load_dashboard_chamber(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
    key: &'static str,
    title: &'static str,
    presider_label: &'static str,
    empty_message: &'static str,
) -> Result<DashboardChamber, String> {
    let rows = sqlx::query(
        "SELECT
            id,
            speaker,
            status::text AS status,
            vote_form,
            mk13_house_id,
            session_kind::text AS session_kind
        FROM legislature_session
        WHERE status != 'Closed'::session_status AND house = $1
        ORDER BY CASE session_kind::text WHEN 'Regular' THEN 0 ELSE 1 END, id",
    )
    .bind(key)
    .fetch_all(db)
    .await
    .map_err(|error| error.to_string())?;

    let has_tabs = rows.len() > 1;
    let mut sessions = Vec::with_capacity(rows.len());

    for row in rows {
        let id: i32 = row.try_get("id").unwrap_or_default();
        let display_id: Option<i32> = row.try_get("mk13_house_id").unwrap_or_default();
        let session_kind_label: String = row
            .try_get("session_kind")
            .unwrap_or_else(|_| "Regular".to_string());
        let speaker: i64 = row.try_get("speaker").unwrap_or_default();
        let tab_key = session_kind_label.to_lowercase().replace(' ', "-");

        sessions.push(DashboardSession {
            id,
            display_name: display_session_name(
                title,
                &session_kind_label,
                display_id.unwrap_or(id),
            ),
            session_kind_label,
            status_label: row.try_get("status").unwrap_or_default(),
            vote_form: row.try_get("vote_form").unwrap_or_default(),
            presider_label,
            presider: resolve_author(author_lookup, speaker).await,
            tab_id: format!("dashboard-{key}-{tab_key}-tab"),
            panel_id: format!("dashboard-{key}-{tab_key}-panel"),
            bills: load_dashboard_session_bills(db, author_lookup, id).await?,
            motions: load_dashboard_session_motions(db, author_lookup, id).await?,
        });
    }

    Ok(DashboardChamber {
        key,
        title,
        empty_message,
        has_sessions: !sessions.is_empty(),
        has_tabs,
        sessions,
    })
}

async fn load_dashboard_executive_bills(
    db: &PgPool,
    author_lookup: &DiscordAuthorLookupClient,
) -> Result<Vec<DashboardExecutiveBillItem>, String> {
    let rows = sqlx::query(
        "SELECT
            id,
            name,
            submitter,
            status,
            CASE
                WHEN executive_deadline_at IS NULL THEN 'No deadline recorded'
                ELSE TO_CHAR(executive_deadline_at, 'YYYY-MM-DD HH24:MI') || ' UTC'
            END AS executive_deadline_label
        FROM bill
        WHERE status = $1
        ORDER BY executive_deadline_at ASC NULLS LAST, id",
    )
    .bind(AWAITING_EXECUTIVE_STATUS)
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
            let submitter: i64 = row.try_get("submitter").unwrap_or_default();
            let status: i32 = row.try_get("status").unwrap_or_default();

            DashboardExecutiveBillItem {
                id,
                name: row.try_get("name").unwrap_or_default(),
                href: detail_href_for_status(id, status),
                author: author_for_submitter(&authors, submitter),
                executive_deadline_label: row
                    .try_get("executive_deadline_label")
                    .unwrap_or_else(|_| "No deadline recorded".to_string()),
            }
        })
        .collect())
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
            bill.html,
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
            bill.html,
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
    let html: String = row.try_get("html").unwrap_or_default();
    let rendered_content = render_bill_content(id, &html, &markdown, &content);

    Ok(Some(BillDetail {
        id: row.try_get("id").unwrap_or_default(),
        name: row.try_get("name").unwrap_or_default(),
        content_html: rendered_content.html,
        content_class: rendered_content.css_class,
        uses_gdoc_html: rendered_content.uses_gdoc_html,
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
        "SELECT id, name, content, markdown, html, link FROM bill WHERE status = $1 ORDER BY id",
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
            let html: String = row.try_get("html").unwrap_or_default();
            let id: i32 = row.try_get("id").unwrap_or_default();
            let rendered_content = render_bill_content(id, &html, &markdown, &content);

            LegalCodeLaw {
                id,
                name: row.try_get("name").unwrap_or_default(),
                content_html: rendered_content.html,
                content_class: rendered_content.css_class,
                uses_gdoc_html: rendered_content.uses_gdoc_html,
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
            child.html,
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
        let child_html: String = row.try_get("html").unwrap_or_default();
        let rendered_content =
            render_bill_content(child_id, &child_html, &child_markdown, &child_content);

        amendments_by_parent
            .entry(parent_id)
            .or_default()
            .push(LegalCodeAmendmentEntry {
                href: law_anchor_href(child_id),
                context_label: format!("Amendment to Law #{parent_id}"),
                law: LegalCodeLaw {
                    id: child_id,
                    name: row.try_get("name").unwrap_or_default(),
                    content_html: rendered_content.html,
                    content_class: rendered_content.css_class,
                    uses_gdoc_html: rendered_content.uses_gdoc_html,
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

    let has_gdoc_html = sections.iter().any(|section| section.law.uses_gdoc_html);

    Ok(LegalCodePageData {
        total_count: sections.len(),
        sections,
        index_sections,
        has_gdoc_html,
    })
}

fn normalize_requested_asset_path(path: &PathBuf) -> Option<String> {
    let mut cleaned = Vec::new();

    for component in path.components() {
        match component {
            Component::Normal(segment) => {
                let value = segment.to_string_lossy();
                if value.is_empty() {
                    continue;
                }
                cleaned.push(value.into_owned());
            }
            Component::CurDir => continue,
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => return None,
        }
    }

    if cleaned.is_empty() {
        None
    } else {
        Some(cleaned.join("/"))
    }
}

fn content_type_for_asset_path(path: &str) -> ContentType {
    let extension = path
        .rsplit('.')
        .next()
        .unwrap_or_default()
        .to_ascii_lowercase();

    match extension.as_str() {
        "css" => ContentType::CSS,
        "gif" => ContentType::GIF,
        "htm" | "html" => ContentType::HTML,
        "jpeg" | "jpg" => ContentType::JPEG,
        "js" => ContentType::JavaScript,
        "json" => ContentType::JSON,
        "pdf" => ContentType::PDF,
        "png" => ContentType::PNG,
        "svg" => ContentType::parse_flexible("image/svg+xml").unwrap_or(ContentType::Binary),
        "txt" => ContentType::Plain,
        "webp" => ContentType::parse_flexible("image/webp").unwrap_or(ContentType::Binary),
        _ => ContentType::Binary,
    }
}

async fn load_bill_pdf(db: &PgPool, id: i32, laws_only: bool) -> Result<Option<Vec<u8>>, String> {
    let query = if laws_only {
        "SELECT pdf FROM bill WHERE id = $1 AND status = $2"
    } else {
        "SELECT pdf FROM bill WHERE id = $1"
    };

    let mut statement = sqlx::query(query).bind(id);
    if laws_only {
        statement = statement.bind(LAW_STATUS);
    }

    let row = statement
        .fetch_optional(db)
        .await
        .map_err(|error| error.to_string())?;

    let Some(row) = row else {
        return Ok(None);
    };

    Ok(row.try_get::<Option<Vec<u8>>, _>("pdf").unwrap_or_default())
}

// todo: do it once
async fn load_bill_asset(
    db: &PgPool,
    id: i32,
    asset_path: &str,
) -> Result<Option<(ContentType, Vec<u8>)>, String> {
    let row = sqlx::query("SELECT html_zip FROM bill WHERE id = $1")
        .bind(id)
        .fetch_optional(db)
        .await
        .map_err(|error| error.to_string())?;

    let Some(row) = row else {
        return Ok(None);
    };

    let Some(html_zip) = row
        .try_get::<Option<Vec<u8>>, _>("html_zip")
        .unwrap_or_default()
    else {
        return Ok(None);
    };

    let cursor = Cursor::new(html_zip);
    let mut archive = ZipArchive::new(cursor).map_err(|error| error.to_string())?;
    let Ok(mut file) = archive.by_name(asset_path) else {
        return Ok(None);
    };

    let mut bytes = Vec::new();
    std::io::Read::read_to_end(&mut file, &mut bytes).map_err(|error| error.to_string())?;

    Ok(Some((content_type_for_asset_path(asset_path), bytes)))
}

#[get("/")]
async fn index(state: &State<AppState>) -> Result<Template, String> {
    let recent_laws = load_recent_dashboard_laws(&state.db).await?;
    let senate = load_dashboard_chamber(
        &state.db,
        &state.author_lookup,
        "senate",
        "Senate",
        "Senator Presiding",
        "There is no open session in the Senate right now.",
    )
    .await?;
    let commons = load_dashboard_chamber(
        &state.db,
        &state.author_lookup,
        "commons",
        "Commons",
        "Speaker",
        "There is no open session in the Commons right now.",
    )
    .await?;
    let executive_bills = load_dashboard_executive_bills(&state.db, &state.author_lookup).await?;

    Ok(Template::render(
        "index",
        context! {
            recent_laws,
            senate,
            commons,
            executive_bills,
        },
    ))
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

#[get("/bill/<id>/pdf")]
async fn bill_pdf(
    id: i32,
    state: &State<AppState>,
) -> Result<Option<(ContentType, Vec<u8>)>, String> {
    Ok(load_bill_pdf(&state.db, id, false)
        .await?
        .map(|pdf| (ContentType::PDF, pdf)))
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

#[get("/law/<id>/pdf")]
async fn law_pdf(
    id: i32,
    state: &State<AppState>,
) -> Result<Option<(ContentType, Vec<u8>)>, String> {
    Ok(load_bill_pdf(&state.db, id, true)
        .await?
        .map(|pdf| (ContentType::PDF, pdf)))
}

#[get("/legal-code")]
async fn legal_code(state: &State<AppState>) -> Result<Template, String> {
    let legal_code = load_legal_code(&state.db).await?;
    let total_count = legal_code.total_count;
    let sections = legal_code.sections;
    let index_sections = legal_code.index_sections;
    let has_gdoc_html = legal_code.has_gdoc_html;

    Ok(Template::render(
        "legal_code",
        context! {
            sections,
            index_sections,
            total_count,
            has_gdoc_html,
        },
    ))
}

#[get("/_bill-asset/<id>/<path..>")]
async fn bill_asset(
    id: i32,
    path: PathBuf,
    state: &State<AppState>,
) -> Result<Option<(ContentType, Vec<u8>)>, String> {
    let Some(asset_path) = normalize_requested_asset_path(&path) else {
        return Ok(None);
    };

    load_bill_asset(&state.db, id, &asset_path).await
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
                bill_pdf,
                law_index,
                law,
                law_pdf,
                legal_code,
                bill_asset
            ],
        )
        .attach(Template::fairing())
        .mount("/static", FileServer::from("static"))
        .register("/", catchers![not_found])
}

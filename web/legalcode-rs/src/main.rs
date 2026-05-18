#[macro_use]
extern crate rocket;

use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use rocket::{State, fs::FileServer};
use rocket_dyn_templates::{Template, context};
use serde::Serialize;
use sqlx::{PgPool, Row};

const LAW_STATUS: i32 = 10; // siehe bot/utils/modules.py BillIsLaw

struct AppState {
    db: PgPool,
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
}

#[derive(Serialize, Clone)]
struct MotionListItem {
    row_id: String,
    id: i32,
    title: String,
    body: String,
    excerpt: String,
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
    content: String,
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
    sponsor_count: i64,
    history: Vec<BillHistoryItem>,
}

#[derive(Serialize, Clone)]
struct LegalCodeItem {
    id: i32,
    name: String,
    content: String,
    link: String,
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

async fn load_motion_list(db: &PgPool) -> Result<Vec<MotionListItem>, String> {
    let rows = sqlx::query("SELECT id, title, description FROM motion ORDER BY id")
        .fetch_all(db)
        .await
        .map_err(|error| error.to_string())?;

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();
            let title: String = row.try_get("title").unwrap_or_default();
            let body: String = row.try_get("description").unwrap_or_default();

            MotionListItem {
                row_id: format!("motion-{id}"),
                id,
                title,
                excerpt: make_excerpt(&body, 50),
                body,
            }
        })
        .collect())
}

async fn load_motion_detail(db: &PgPool, id: i32) -> Result<MotionDetail, String> {
    let row = sqlx::query("SELECT id, title, description FROM motion WHERE id = $1")
        .bind(id)
        .fetch_one(db)
        .await
        .map_err(|_| "Motion not found".to_string())?;

    Ok(MotionDetail {
        id: row.try_get("id").unwrap_or_default(),
        title: row.try_get("title").unwrap_or_default(),
        body: row.try_get("description").unwrap_or_default(),
    })
}

async fn load_bill_list(db: &PgPool, laws_only: bool) -> Result<Vec<BillListItem>, String> {
    let query = if laws_only {
        "SELECT
            bill.id,
            bill.name,
            bill.content,
            bill.link,
            bill.submitter_description,
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

    Ok(rows
        .into_iter()
        .map(|row| {
            let id: i32 = row.try_get("id").unwrap_or_default();
            let name: String = row.try_get("name").unwrap_or_default();
            let content: String = row.try_get("content").unwrap_or_default();
            let link: String = row.try_get("link").unwrap_or_default();
            let submitter_description: String =
                row.try_get("submitter_description").unwrap_or_default();
            let origin_house: String = row.try_get("origin_house").unwrap_or_default();
            let origin_house_label = display_house_name(&origin_house);
            let is_procedure: bool = row.try_get("is_procedure").unwrap_or_default();
            let status: i32 = row.try_get("status").unwrap_or_default();

            BillListItem {
                row_id: format!("bill-{id}"),
                id,
                name,
                excerpt: make_excerpt(&content, 50),
                content,
                link,
                submitter_description,
                origin_house,
                origin_house_label: origin_house_label.clone(),
                type_label: display_type_label(&origin_house_label, is_procedure),
                is_procedure,
                status,
                status_label: display_bill_status(status).to_string(),
                is_law: status == LAW_STATUS,
                sponsor_count: row.try_get("sponsor_count").unwrap_or_default(),
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
    id: i32,
    laws_only: bool,
    include_history: bool,
) -> Result<BillDetail, String> {
    let query = if laws_only {
        "SELECT
            bill.id,
            bill.name,
            bill.content,
            bill.link,
            bill.submitter_description,
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
            bill.link,
            bill.submitter_description,
            bill.origin_house,
            bill.is_procedure,
            bill.status,
            COUNT(DISTINCT bill_sponsor.sponsor)::bigint AS sponsor_count
        FROM bill
        LEFT JOIN bill_sponsor ON bill_sponsor.bill_id = bill.id
        WHERE bill.id = $1
        GROUP BY bill.id"
    };

    let not_found = if laws_only {
        "Law not found"
    } else {
        "Bill not found"
    };

    let row = sqlx::query(query)
        .bind(id)
        .fetch_one(db)
        .await
        .map_err(|_| not_found.to_string())?;

    let origin_house: String = row.try_get("origin_house").unwrap_or_default();
    let origin_house_label = display_house_name(&origin_house);
    let is_procedure: bool = row.try_get("is_procedure").unwrap_or_default();
    let status: i32 = row.try_get("status").unwrap_or_default();

    let history = if include_history {
        load_bill_history(db, id).await?
    } else {
        Vec::new()
    };

    Ok(BillDetail {
        id: row.try_get("id").unwrap_or_default(),
        name: row.try_get("name").unwrap_or_default(),
        content: row.try_get("content").unwrap_or_default(),
        link: row.try_get("link").unwrap_or_default(),
        submitter_description: row.try_get("submitter_description").unwrap_or_default(),
        origin_house,
        origin_house_label: origin_house_label.clone(),
        type_label: display_type_label(&origin_house_label, is_procedure),
        is_procedure,
        is_procedure_label: bool_label(is_procedure),
        status,
        status_label: display_bill_status(status).to_string(),
        is_law: status == LAW_STATUS,
        sponsor_count: row.try_get("sponsor_count").unwrap_or_default(),
        history,
    })
}

async fn load_legal_code(db: &PgPool) -> Result<Vec<LegalCodeItem>, String> {
    let rows =
        sqlx::query("SELECT id, name, content, link FROM bill WHERE status = 10 ORDER BY id")
            .fetch_all(db)
            .await
            .map_err(|error| error.to_string())?;

    Ok(rows
        .into_iter()
        .map(|row| LegalCodeItem {
            id: row.try_get("id").unwrap_or_default(),
            name: row.try_get("name").unwrap_or_default(),
            content: row.try_get("content").unwrap_or_default(),
            link: row.try_get("link").unwrap_or_default(),
        })
        .collect())
}

#[get("/")]
async fn index() -> Result<Template, String> {
    Ok(Template::render("index", context! {}))
}

#[get("/motion")]
async fn motion_index(state: &State<AppState>) -> Result<Template, String> {
    let motions = load_motion_list(&state.db).await?;
    let total_count = motions.len();
    let search_items_b64 = encode_json_base64(&motions)?;
    let search_keys_b64 = encode_json_base64(&motion_search_keys())?;

    Ok(Template::render(
        "motions",
        context! {
            motions,
            total_count,
            search_items_b64,
            search_keys_b64,
        },
    ))
}

#[get("/motion/<id>")]
async fn motion(id: i32, state: &State<AppState>) -> Result<Template, String> {
    let motion = load_motion_detail(&state.db, id).await?;

    Ok(Template::render(
        "motion",
        context! {
            motion,
        },
    ))
}

#[get("/bill")]
async fn bill_index(state: &State<AppState>) -> Result<Template, String> {
    let bills = load_bill_list(&state.db, false).await?;
    let total_count = bills.len();
    let status_options = bill_status_options();
    let search_items_b64 = encode_json_base64(&bills)?;
    let search_keys_b64 = encode_json_base64(&bill_search_keys())?;

    Ok(Template::render(
        "bills",
        context! {
            bills,
            total_count,
            status_options,
            search_items_b64,
            search_keys_b64,
        },
    ))
}

#[get("/bill/<id>")]
async fn bill(id: i32, state: &State<AppState>) -> Result<Template, String> {
    let bill = load_bill_detail(&state.db, id, false, true).await?;

    Ok(Template::render(
        "bill",
        context! {
            bill,
        },
    ))
}

#[get("/law")]
async fn law_index(state: &State<AppState>) -> Result<Template, String> {
    let laws = load_bill_list(&state.db, true).await?;
    let total_count = laws.len();
    let search_items_b64 = encode_json_base64(&laws)?;
    let search_keys_b64 = encode_json_base64(&bill_search_keys())?;

    Ok(Template::render(
        "laws",
        context! {
            laws,
            total_count,
            search_items_b64,
            search_keys_b64,
        },
    ))
}

#[get("/law/<id>")]
async fn law(id: i32, state: &State<AppState>) -> Result<Template, String> {
    let law = load_bill_detail(&state.db, id, true, false).await?;

    Ok(Template::render(
        "law",
        context! {
            law,
        },
    ))
}

#[get("/legal-code")]
async fn legal_code(state: &State<AppState>) -> Result<Template, String> {
    let laws = load_legal_code(&state.db).await?;
    let total_count = laws.len();

    Ok(Template::render(
        "legal_code",
        context! {
            laws,
            total_count,
        },
    ))
}

#[launch]
async fn rocket() -> _ {
    let database_url = std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");

    let pool = PgPool::connect(&database_url)
        .await
        .expect("failed to connect to PostgreSQL");

    rocket::build()
        .manage(AppState { db: pool })
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
}

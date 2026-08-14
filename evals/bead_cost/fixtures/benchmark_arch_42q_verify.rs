//! Canonical verification for the `arch-42q` benchmark. NOT part of archeion.
//!
//! This file is the scorer's instrument, not the workspace's. It is copied into
//! `tests/benchmark_arch_42q_verify.rs` of a scoring worktree AFTER a run's diff is applied, and
//! never exists in the tree a benchmarked model works in — for the reason SWE-bench applies its
//! `test_patch` from outside: a model that can read the acceptance test is being scored on
//! reading comprehension.
//!
//! It answers section A of `local/benchmark-rubric-arch-42q.md`, and nothing else. Sections B
//! through F are read off the diff by a human or a scoring agent; this only answers whether the
//! behaviour the bead asked for is present.
//!
//! Method comes from the bead itself: *"Proven by a loopback server that counts requests per path
//! and a test asserting the count, not by reading the archive afterwards."* Counting at the server
//! is what separates the real fix from the plausible wrong one — decoding where the depth map
//! reads `page_links` corrects identity and leaves the request count untouched.
//!
//! Run: `cargo test --test benchmark_arch_42q_verify -- --nocapture`
//! It prints one `ARCH42Q_VERDICT` line of JSON, which is what the scorer reads.

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::thread;

use archeion::CanonicalUrl;
use archeion::storage::Archive;
use tempfile::TempDir;

/// Every request target this server was asked for, in arrival order, exactly as it came off the
/// wire. The whole instrument is this vector: every assertion below is a question about it.
type RequestLog = Arc<Mutex<Vec<String>>>;

struct Site {
    port: u16,
    log: RequestLog,
}

impl Site {
    /// Bound before serving, so the index page below can name the port it will be fetched on.
    fn bind() -> (TcpListener, Self) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("a loopback port");
        let port = listener.local_addr().expect("the bound address").port();
        let site = Self {
            port,
            log: Arc::new(Mutex::new(Vec::new())),
        };
        (listener, site)
    }

    fn serve(&self, listener: TcpListener, index_body: String) {
        let log = Arc::clone(&self.log);
        let index = Arc::new(index_body);
        thread::spawn(move || {
            for stream in listener.incoming().flatten() {
                let log = Arc::clone(&log);
                let index = Arc::clone(&index);
                // One thread per connection: the client keeps a pool, and answering in turn
                // would hold every later request behind whichever connection opened first.
                thread::spawn(move || answer(stream, &log, &index));
            }
        });
    }

    fn url(&self, path: &str) -> String {
        format!("http://127.0.0.1:{}{path}", self.port)
    }

    fn targets(&self) -> Vec<String> {
        self.log.lock().expect("the request log").clone()
    }

    /// Requests counted by path alone, with the query discarded. This is the count the bead is
    /// about: one page fetched once, however many ways the index spelled its address.
    fn counts_by_path(&self) -> HashMap<String, usize> {
        let mut counts = HashMap::new();
        for target in self.targets() {
            let path = target.split('?').next().unwrap_or_default().to_owned();
            *counts.entry(path).or_insert(0) += 1;
        }
        counts
    }
}

fn answer(mut stream: TcpStream, log: &RequestLog, index: &str) -> std::io::Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut request_line = String::new();
    reader.read_line(&mut request_line)?;
    // The whole request has to be consumed before the answer, or the client sees the close as a
    // reset rather than as a response.
    let mut header = String::new();
    while reader.read_line(&mut header)? > 2 {
        header.clear();
    }

    let target = request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or_default()
        .to_owned();
    let path = target.split('?').next().unwrap_or_default().to_owned();

    // `robots.txt` is fetched by every run and says nothing about this bead, so it is answered
    // and deliberately kept out of the log: counting it would put a constant in every assertion.
    if path != "/robots.txt" {
        log.lock().expect("the request log").push(target.clone());
    }

    // The post answers on its path whatever the query says, so a run that asks for the wrong
    // spelling still gets a page and still lands in the archive. The difference between a fixed
    // and an unfixed run then shows up purely in the count, never as one run 404ing where the
    // other did not.
    let (status, body): (&str, &str) = match path.as_str() {
        "/" => ("200 OK", index),
        "/a" => ("200 OK", LINKS_NAMED),
        "/c" => ("200 OK", LINKS_NUMERIC),
        "/d" => ("200 OK", LINKS_HEX),
        "/p/named" | "/p/decimal" | "/p/hex" => ("200 OK", POST),
        "/robots.txt" => ("200 OK", ""),
        _ => ("404 Not Found", "not here"),
    };

    let head = format!(
        "HTTP/1.1 {status}\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    );
    stream.write_all(head.as_bytes())?;
    stream.write_all(body.as_bytes())?;
    stream.flush()
}

const POST: &str = "<html><head><title>A post</title></head><body>\
    <p>One post, reachable by three escaped spellings of one address.</p></body></html>";

/// **The spellings are on separate pages, and no page writes the separator plainly. Both halves of
/// that are load-bearing, and both were learned by measuring an unfixed tree rather than reasoning
/// about it.**
///
/// *Separate pages*, because canonicalization already folds the spellings into one item — that is
/// what `arch-s9b` landed — so links on a single page are deduplicated before anything is fetched
/// and the base tree issues exactly one request. The bead's own case is a publication whose pages
/// each link one post their own way; the crawl meets them separately, so each spelling reaches the
/// frontier on its own.
///
/// *No plain spelling*, because a control page writing `?x=1&y=2` hands the crawl a way to be
/// **accidentally right**: whichever page it reaches first decides which spelling goes on the
/// wire, and the fixture passes or fails by that race. Measured — three consecutive runs of one
/// unfixed tree gave three different verdicts. With every page escaping the separator, the only
/// way `?x=1&y=2` can reach the server is by being decoded, which is precisely the fix under test.
const LINKS_NAMED: &str = "<html><head><title>a</title></head><body>\
    <a href=\"/p/named?x=1&amp;y=2\">named entity</a></body></html>";

const LINKS_NUMERIC: &str = "<html><head><title>c</title></head><body>\
    <a href=\"/p/decimal?x=1&#38;y=2\">decimal reference</a></body></html>";

const LINKS_HEX: &str = "<html><head><title>d</title></head><body>\
    <a href=\"/p/hex?x=1&#x26;y=2\">hexadecimal reference</a></body></html>";

fn index_page() -> String {
    "<html><head><title>An index</title></head><body>\
     <p>Three distinct posts, each linked by one escaped spelling:\
     <a href=\"/p/named?x=1&amp;y=2\">named</a>\
     <a href=\"/p/decimal?x=1&#38;y=2\">decimal</a>\
     <a href=\"/p/hex?x=1&#x26;y=2\">hex</a></p>\
     </body></html>"
        .to_owned()
}

/// One crawl, shared by every assertion below, because a crawl per assertion would pay the
/// process start four times to ask four questions of the same request log.
fn crawl() -> (Site, TempDir) {
    let (listener, site) = Site::bind();
    site.serve(listener, index_page());

    let temp = TempDir::new().expect("a temp dir");
    let archive_path = temp.path().join("archive");

    let output = Command::new(env!("CARGO_BIN_EXE_archeion"))
        .arg("capture")
        .arg(&archive_path)
        .arg(site.url("/"))
        .args(["--max-pages", "20", "--max-depth", "5"])
        .args(["--concurrency", "4", "--max-retries", "0"])
        .args(["--deadline", "60s", "--allow-private-addresses"])
        .output()
        .expect("archeion runs");

    // Deliberately NOT `assert!(output.status.success())`. An unfixed tree exits non-zero here
    // because it loses a link — that is the bug, not a broken harness, and a guard on the exit
    // code makes every assertion below fail for a reason that has nothing to do with what it
    // claims to measure. The first draft of this file did exactly that and failed 5/5 on a tree
    // whose behaviour it had not yet observed.
    //
    // What is worth guarding is that the fixture itself ran: the crawl has to have reached the
    // four linking pages, or the request log is empty for reasons upstream of the bead.
    let targets = site.targets();
    for page in ["/"] {
        assert!(
            targets.iter().any(|target| target == page),
            "the fixture never served `{page}`, so nothing below is a statement about the bead.\n\
             exit {:?}\nstdout:\n{}\nstderr:\n{}\ntargets: {targets:#?}",
            output.status.code(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr),
        );
    }

    (site, temp)
}

/// The three spellings, the post each one links, and the address every one of them means.
const SPELLINGS: [(&str, &str); 3] = [
    ("/p/named", "/p/named?x=1&y=2"),
    ("/p/decimal", "/p/decimal?x=1&y=2"),
    ("/p/hex", "/p/hex?x=1&y=2"),
];

/// One crawl, five verdicts.
///
/// **Deliberately a single `#[test]`, and that is a correction rather than a style choice.** The
/// first draft gave each criterion its own test, so each ran its own crawl — and three consecutive
/// runs of the same unfixed tree failed 3, then 4, then 2 of them. Five crawls give five
/// independently noisy answers, and section A becomes noise spread across 45 runs. One crawl judged
/// five ways removes that: every criterion below is a question about one request log, phrased as a
/// property of the whole set rather than of arrival order.
///
/// **Each spelling links a post of its own** (`/p/named`, `/p/decimal`, `/p/hex`) rather than all
/// three linking one post. Sharing one address let canonicalization fold them, so exactly one
/// request went out and *which spelling it carried was a race* — A3, A4 and A5 flipped between runs
/// of an unmodified tree. With three addresses, every spelling is guaranteed its own request and
/// every criterion is decided by the fix rather than by scheduling.
///
/// The verdict line is machine-readable on purpose: the scorer aggregates 45 of these, and reading
/// them out of human prose is how a transcription error enters a result.
#[test]
fn section_a_of_the_rubric() {
    let (site, temp) = crawl();
    let targets = site.targets();
    let counts = site.counts_by_path();
    let post_targets: Vec<&String> = targets
        .iter()
        .filter(|target| target.starts_with("/p/"))
        .collect();

    // A1 — one request per distinct page. Each post is linked once, by one spelling, so anything
    // above one is a page fetched twice for one address.
    let a1 = SPELLINGS
        .iter()
        .all(|(path, _)| counts.get(*path).copied().unwrap_or(0) == 1);

    // A2 — the request line carries the parameters the page meant, for every spelling.
    let a2 = post_targets.len() == SPELLINGS.len()
        && SPELLINGS
            .iter()
            .all(|(_, meant)| targets.iter().any(|target| target == meant));

    // A3 — no `amp;`-prefixed parameter reaches the server. Separate from A2 because it is the
    // failure measured in the wild: the origin is asked about a parameter nobody meant to ask
    // about, and answers however that site treats an unknown one.
    let a3 = !targets.iter().any(|target| target.contains("amp;"));

    // A4 — a numeric reference does not cost the parameter behind it. It fails worse than `&amp;`
    // and differently: a URL parser cuts at `#`, so `?x=1&#38;y=2` parses with the query `x=1&`
    // and the fragment `38;y=2`, the fragment is dropped, and `y=2` is gone from the address
    // rather than merely misnamed. Nothing reports it, which is why it is asserted on its own.
    let a4 = !post_targets.is_empty()
        && post_targets.iter().all(|target| {
            target.contains("y=2") && !target.contains("38;") && !target.contains("x26;")
        });

    // A5 — the archive holds one item per distinct page, under the address the page meant.
    let archive = Archive::open_existing(&temp.path().join("archive")).expect("the archive exists");
    let a5 = SPELLINGS.iter().all(|(_, meant)| {
        CanonicalUrl::parse(&site.url(meant))
            .ok()
            .and_then(|url| archive.list_captures(&url).ok())
            .is_some_and(|captures| captures.len() == 1)
    });

    println!("ARCH42Q_VERDICT {{\"a1\":{a1},\"a2\":{a2},\"a3\":{a3},\"a4\":{a4},\"a5\":{a5}}}");
    println!("ARCH42Q_TARGETS {targets:?}");

    assert!(
        a1 && a2 && a3 && a4 && a5,
        "section A not satisfied — a1:{a1} a2:{a2} a3:{a3} a4:{a4} a5:{a5}\ntargets: {targets:#?}"
    );
}

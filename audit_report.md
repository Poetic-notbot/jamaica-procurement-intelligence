# Data Audit Report — Jamaica Procurement OS
**Schema Version:** v2 | **Status:** Active

---

## 1. Schema — contract_awards
| Field | Type | Constraint |
|-------|------|-----------|
| id | INTEGER PK | Auto |
| procurement_method | TEXT | |
| procuring_entity | TEXT | Indexed |
| title | TEXT | |
| contract_amount_jmd | REAL | Cleaned float |
| publication_date | TEXT | ISO-8601 |
| notice_pdf_url | TEXT | |
| source_url | TEXT | |
| normalized_category | TEXT | 18-category taxonomy |
| category_confidence | REAL | 0.0-0.98 |
| supplier_name | TEXT | Extracted where available |
| scraped_at | DATETIME | UTC |
| data_hash | TEXT UNIQUE | MD5 dedup key |

## 2. Schema — opened_bids
| Field | Type | Constraint |
|-------|------|-----------|
| id | INTEGER PK | Auto |
| cft_title | TEXT | |
| reference_number | TEXT | |
| procuring_entity | TEXT | Indexed |
| submission_deadline | TEXT | ISO-8601 |
| award_date | TEXT | ISO-8601 |
| procurement_method | TEXT | |
| status | TEXT | |
| opened_bids_url | TEXT | |
| normalized_category | TEXT | 18-category taxonomy |
| category_confidence | REAL | |
| bidder_count | INTEGER | Competition metric |
| data_hash | TEXT UNIQUE | MD5 dedup key |

## 3. Data Quality Rules
- **Amounts:** Numeric REAL only. Range 0 < x < 10T JMD. Strip JMD/$/, commas.
- **Dates:** ISO-8601 YYYY-MM-DD. 10 input formats accepted. NULL if unparseable.
- **Deduplication:** Awards: hash(entity+title+date). Bids: hash(ref+title+entity). ON CONFLICT DO NOTHING.
- **Categories:** 18-category taxonomy. Confidence 0-0.98. Uncategorized if no match.

## 4. New Tables (v2)
| Table | Purpose |
|-------|---------|
| suppliers | Aggregated supplier intelligence |
| competition_metrics | Avg/median bidders per category |
| supplier_profiles | Compliance vault — TRN, TCC, NCC |
| watchlists | User-tracked buyers/suppliers/categories |
| audit_log | Scraper run metadata |

## 5. Data Sources
| Source | URL | Est. Records |
|--------|-----|-------------|
| Contract Awards | https://www.gojep.gov.jm/epps/viewCaNotices.do | 12,304 |
| Opened Bids | https://www.gojep.gov.jm/epps/common/viewOpenedTenders.do | 77,656 |

## 6. Known Limitations
- Supplier names not consistently published on GOJEP public pages
- Bid opening PDFs not yet parsed for supplier extraction
- Bidder count requires deep scraping of individual bid opening pages
- Rate limiting: 1.5s per page to respect GOJEP server

## 7. Audit Checklist (run after each scraper batch)
- [ ] Total awards count
- [ ] Null contract_amount_jmd count
- [ ] Null publication_date count
- [ ] Duplicate hash collisions (target: 0)
- [ ] Uncategorized % (target: <20%)
- [ ] Low confidence % (target: <30%)

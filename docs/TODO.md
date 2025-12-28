# Zunkiree Search v1 - TODO

> Last Updated: December 28, 2024

---

## 1. BLOCKED (Action Required)

| Task | Action | Link |
|------|--------|------|
| Add OpenAI credits | Add $5-10 to OpenAI account | https://platform.openai.com/settings/organization/billing/overview |

**Everything below is blocked until OpenAI credits are added.**

---

## 2. NEXT (Immediately After Blocker Resolved)

Priority order:

- [ ] **Ingest ZunkireeLabs content**
  - Open admin panel: https://zunkiree-admin.vercel.app
  - Use admin key: `zunkiree2024`
  - Customer: `zunkireelabs`
  - Ingest via URL: https://zunkireelabs.com (or relevant pages)
  - Or ingest via text: Copy/paste key content

- [ ] **Test end-to-end query flow**
  - Go to dev-web.zunkireelabs.com
  - Click the widget
  - Ask a question about ZunkireeLabs
  - Verify AI response comes from ingested content

- [ ] **Verify sources display**
  - Check that source links appear with answers
  - Confirm clicking sources works

- [ ] **Widget config tuning** (if needed)
  - Adjust tone (formal/neutral/friendly)
  - Update welcome message
  - Customize fallback message

---

## 3. PILOT CUSTOMERS (After ZunkireeLabs Works)

| Customer | Site ID | Domain | Data Source | Status |
|----------|---------|--------|-------------|--------|
| Admizz Education | `admizz` | admizz.com | Country pages, FAQs | Not started |
| Khems Cleaning | `khems` | khemsnepal.com | Services, pricing | Not started |
| Guntabya OTA | `guntabya` | guntabya.com | Listings, policies | Not started |

**For each pilot:**
1. Create customer via admin panel
2. Ingest their content
3. Generate embed code
4. Send to customer for integration
5. Test on their site

---

## 4. BACKLOG (Future Enhancements)

### High Priority
- [ ] Analytics dashboard (query volume, popular questions)
- [ ] Rate limiting per customer
- [ ] Usage tracking and billing metrics
- [ ] Email notifications for ingestion failures

### Medium Priority
- [ ] Additional LLM providers (Anthropic Claude, Azure OpenAI)
- [ ] Custom domain support for widget CDN
- [ ] Bulk ingestion (sitemap crawling)
- [ ] Scheduled re-ingestion (content freshness)
- [ ] Query caching for common questions

### Low Priority
- [ ] Multi-language support
- [ ] Voice input for widget
- [ ] Widget themes (dark mode, custom CSS)
- [ ] Conversation history (multi-turn)
- [ ] Export query logs as CSV

---

## 5. TECHNICAL DEBT

- [ ] Add unit tests for backend services
- [ ] Add integration tests for API endpoints
- [ ] Set up CI/CD pipeline (GitHub Actions)
- [ ] Add request logging middleware
- [ ] Implement proper error tracking (Sentry)
- [ ] Add health check for external dependencies (OpenAI, Pinecone)
- [ ] Review and rotate API keys/secrets
- [ ] Add database migrations (Alembic)

---

## 6. DOCUMENTATION (Nice to Have)

- [ ] Customer onboarding guide
- [ ] Widget customization guide
- [ ] Troubleshooting guide
- [ ] API reference with examples
- [ ] Video demo/walkthrough

---

## Quick Reference

### Production URLs
| Service | URL |
|---------|-----|
| Backend API | https://zunkiree-search-v1-production.up.railway.app |
| Widget CDN | https://zunkiree-search-v1.vercel.app |
| Admin Panel | https://zunkiree-admin.vercel.app |
| API Docs | https://zunkiree-search-v1-production.up.railway.app/docs |

### Credentials (Production)
| Key | Value |
|-----|-------|
| Admin Key | `zunkiree2024` |
| ZunkireeLabs Site ID | `zunkireelabs` |
| ZunkireeLabs API Key | `zk_live_zunkireelabs_kFgdkzGSASr_8-olH3Y0SnsWU9GnAV_b` |

### Widget Embed Code (ZunkireeLabs)
```html
<script
  src="https://zunkiree-search-v1.vercel.app/zunkiree-widget.iife.js"
  data-site-id="zunkireelabs"
  data-api-url="https://zunkiree-search-v1-production.up.railway.app"
></script>
```

---

*Update this file as tasks are completed or new items are identified.*

# Interface and reliability audit — 2026-10-23

Scope: improve the existing local photo/video/music gallery, its administration tools, uploads, translations, and permissions. No new product features were added. Existing comments, ratings, CSV, console recovery, profile editing, the API viewer, local-network startup, and large-media uploads remain supported.

## Findings and corrections

| Area | Finding | Correction and evidence |
| --- | --- | --- |
| Upload reliability | A remembered client manifest could become stale after cancellation, expiry, or a lost response. A completed finalization still validated retried metadata. Timestamp-based filesystem locks could remain stale after a crash. | The client refreshes the acknowledged state before resuming, restarts expired/cancelled sessions, and handles transient DB failures as retryable. Completed finalization is idempotent before metadata validation. OS locks release on process exit. Tests inject a finalization DB failure, verify exact preserved bytes, and kill a lock-owning process. Oversized form requests are rejected before body parsing. Managed upload files are released after committed deletion/replacement only when no post still references them; rollback and external-file preservation are tested. Upload ownership history survives account deletion so later file cleanup remains reliable. |
| Performance | The feed rendered the complete collection. Joined ratings and comments multiplied database rows. Feed players requested metadata without user interaction. Hidden app players could continue playing/buffering. | The feed is bounded to 18 items per page. Indexed independent subqueries compute summaries. Feed players use `preload=none`; app navigation pauses/releases hidden players. Added indexes cover feed ordering, comments per post, upload expiry, and file/poster reference lookup. Tests verify stable query counts and correct means/counts with many comments. A local home request used 5 SQL queries. |
| Usability | Upload validation errors did not identify fields. Missing media produced broken elements. Login did not return to the requested post. GET could log a user out. | Upload errors are associated with fields and focus the first invalid control. Images/players have readable fallback states. Login accepts a safe same-host return URL. Logout is a CSRF-protected POST. Oversized avatars produce a normal form error. |
| Mobile layout | Compact controls, wide tables, fixed navigation during text entry, and narrow video detail views reduced usability. | Gallery captions and actions have larger touch targets. Tables scroll inside their own blocks. Focused inputs hide the bottom navigation on small screens. Video details use the full content width; image details retain an image-first layout. |
| Design and language | The visual emphasis was on green panels and utility controls rather than media. There were missing translations and inconsistent player styles. | Neutral charcoal surfaces, restrained lime accents, edge-to-edge media, quieter captions, consistent error/focus states, async image decoding, and readable formatting of client assets. RU/EN strings and compiled catalogs were updated. Reduced-motion settings are respected. |
| Permissions and code | Raw `/media/` URLs bypassed post visibility checks. Staff status alone granted draft viewing. Repeated engagement/visibility logic risked inconsistent behavior. | Registered media URLs, streaming routes, moderation lists, and native foreign-key selectors now use the same visibility policy. Upload manifests are explicitly non-cacheable. Stale saved upload IDs recover even when the server returns an HTML 404 instead of JSON. Draft viewing requires active staff plus view/change permission. A shared query module centralizes that policy and engagement summaries. Absolute server paths remain absent from API/CSV. Tests cover anonymous readers, ordinary users, staff without model permissions, and authorized administrators. |

## Validation

Final validation:

- 116 automated tests pass; Django system checks and migration consistency checks pass.
- Static assets collect successfully; changed JavaScript files pass syntax checks.
- 120 browser route/language/viewport combinations pass: 15 authenticated routes × RU/EN × widths 320, 390, 768, and 1440. No horizontal document overflow was found.
- Browser flows pass for CSV export → preview → import, bulk publish/draft, comments and escaped user text, ratings, deletion confirmation, avatar upload, protected logout, console password recovery, app back/forward, and release of hidden players.
- Real upload browser test: 8 MiB acknowledged → pause → server process restart → browser reload → same file selected → resume → playable final media. A failed final metadata response is retried without retransferring acknowledged bytes. An additional browser probe verifies recovery from a stale saved ID and an actual HTML 404.
- A fresh ordinary-user context cannot fetch the draft page, its original `/media/` path, or its streaming URL. Custom 403/404/500 pages render correctly with DEBUG disabled. JavaScript exception collection is empty.
- A local authenticated home request uses 5 SQL queries. Separate regression tests verify that increasing card count does not introduce per-card SQL queries and that many comments do not inflate rating averages/counts.
 Regression tests include the original flows plus direct draft-file access, shared image references, avatar serving, safe login redirects, CSRF logout, bounded feed/query counts, deferred media loading, readable error pages, failure recovery, and process-crash lock release.

Browser checks use an isolated copy of the database and media. QA accounts, fixture movies, passwords, generated fixture images, browser binaries, and screenshots are not committed to the repository.

## Operating boundaries

- The target remains a local/household HTTP deployment using Django's development server. `check --deploy` reports five expected production configuration warnings: DEBUG, HTTPS redirect/HSTS, and secure session/CSRF cookies. Enabling secure cookies without HTTPS would break the authorized local workflow. These warnings are not suppressed, and this audit does not certify public production hosting.
- A reverse proxy must not directly expose the original `media/uploads` or `media/posters` directories: requests must reach the registered media views to enforce draft visibility. Publicly published media remains accessible through the existing public read-only API behavior.
- Upload logic is tested at the 30 GiB manifest boundary and at byte offsets above 32 bits using sparse files. Browser transfer tests use a small real multi-part file, rather than a 30 GiB movie.
- Linux process-crash locking is exercised here. The Windows branch uses the standard `msvcrt` byte-range lock and needs an actual Windows machine for platform-specific verification. Cross-device Wi-Fi behavior also requires the user's own network.
- Playback depends on the browser and file codec. The site does not transcode movies. Unsupported files retain a download link.
- Files already downloaded by a client cannot be revoked. Visibility checks prevent new unauthorized requests; they cannot erase copies previously received while a post was public.
- No existing user media was pruned or rewritten during the audit. Managed, no-longer-referenced uploaded files are now removed after committed post deletion/replacement; external originals and loose legacy files remain untouched. The existing expired-upload cleanup policy remains in place.

## Updating the local project

Stop the server, run `git pull origin main` and `python manage.py migrate`, then restart the server and refresh with Ctrl+F5. No new runtime dependency is required.


## Follow-up: automatic video covers

The initial `preload=none` feed optimization left videos without a poster blank until playback. Such videos now decode a paused frame near the start of the clip when they approach the viewport. Explicit posters skip this work. The same behavior covers dynamically inserted application thumbnails and detail players. Preview handlers yield immediately to user interaction and are removed when the preview finishes or its element is removed. No automatic playback or sound is introduced.

Validation: all 116 Django tests pass. Dedicated Chromium checks at widths 390 and 1440 verify an actual decoded, non-blank frame from the 2560×1440 H.264/AAC aurora clip, zero preview play events, unchanged unmuted playback, no video requests for explicit posters, and deferred offscreen requests. Further checks verify decoded AAC audio on manual playback, app thumbnails and back/forward release, download/error fallback for missing files, no horizontal overflow, and no JavaScript exceptions. Other browsers continue to depend on their own codec support. Existing files and schema remain unchanged.


## Follow-up: silent hover playback

Feed videos and application video cards now support mouse-only, delayed, muted hover playback. Hover state owns only the temporary preview: leaving restores the prior position and settings, while an explicit click gives playback back to the normal player. Native controls are hidden during the hover preview so a click can reliably promote it to normal playback instead of being consumed by the browser's temporary Pause control. Already active normal players prevent hover playback from starting. Manual playback stops any hover preview. Removed/hidden cards and hidden tabs release previews.

Validation: 116 Django tests pass. Chromium checks exercise silent hover and leave, restoration of position/mute/loop/volume, an actual mouse click to enter unmuted normal playback, continued playback after leaving, priority for an already playing movie and audio, cancellation when music starts, hover with an explicit poster, application navigation releasing thumbnails without inheriting muted state, and touch-device suppression. No JavaScript exceptions occurred. Existing still-frame and error/download behaviors remain supported; browser autoplay and codec rules still apply.


## Follow-up: six media presentation refinements

1. Replaced the feed's masonry columns with an aligned responsive grid and stable 4:3 media stages. Portrait cropping is confined to feed cards; detail images remain contained. Long card titles occupy at most two lines.
2. Automatic covers now use 12% of duration, capped at 3 seconds. A 16×9 pixel brightness sample permits one further seek for a nearly black opening, capped at 6 seconds. Explicit posters and cross-origin decoder restrictions remain respected. Data saver disables the extra sample.
3. Added fixed-geometry loading placeholders and fades to initial and dynamically inserted media. Failed and detached application images are handled without throwing. Reduced motion disables decorative animation.
4. Hover previews last at most four seconds and fade back to the saved position. Existing manual playback, music priority, mute/volume/loop restoration, click takeover, and touch suppression remain supported.
5. Added a two-slot queue for initial frame decoding (one slot with data saver/2G), cancellation for removed/hidden cards, and suppressed automatic hover on constrained connections. Removed redundant `load()` calls that caused duplicated initial range requests. Streaming still uses the existing protected HTTP range route; original file compression/format is unchanged.
6. Unified mobile media geometry, safe long-heading wrapping, compact metadata, and download/navigation touch targets.

Validation before GitHub update: 116 Django tests pass; migration consistency, static collection, and JavaScript syntax checks pass. Chromium layout checks pass for 80 route/language/viewport cases (RU/EN; widths 320, 390, 768, 1440, 1920; feed, application, API viewer, video/image details, profile editing, uploads, dashboard). Checks verify equal stage proportions, bounded long titles, no horizontal overflow, and no JavaScript exceptions. A real black-intro H.264 fixture selects the subsequent orange frame without playback. Hover stops at four seconds. A delayed image retains exactly its reserved height. Two distinct nearby videos are the only pending preview requests under an intentionally blocked transfer; removing queued cards prevents further requests, and queued hidden cards retry when shown again. A throttled 128 KiB/s connection with 180 ms latency decodes a non-black frame from the small fixture in about 2.3 seconds; this is not a throughput guarantee for large originals. Data saver, reduced motion, manual sound, app navigation, missing-file fallback, and detached-image errors are covered. Final still-preview and hover regressions also pass.

Browser checks emulate mobile geometry and touch in Chromium on Linux. Actual phone Safari/Chrome and the user's Wi-Fi must still be checked on the device. No user media, database contents, or upload policy was changed by these refinements.

## Follow-up: VEYRA branding — 2026-10-24

Replaced the generic site identity with VEYRA and a compact folded V mark adapted as an editable SVG. A shared logo partial keeps the main sidebar, mobile/guest header, management sidebar, native Django administration, and error pages consistent. The login editorial illustration uses the same mark. Footer labels, anonymous-author fallbacks, browser titles (including profile/edit/upload pages), local sender identity, RU/EN catalogs, application manifest, and service-worker cache identity were updated. New SVG/PNG favicons, Apple touch icon, and 192/512 application icons replace the generic M tile. Legacy cache prefixes remain recognized only for cleanup. No user accounts, media, database schema, API identifiers, or repository URLs were renamed.

Validation: 116 Django tests pass; system/migration checks, static collection, catalog compilation/checks, and JavaScript syntax checks pass. Chromium verifies 144 route/language/viewport combinations: five guest routes plus thirteen authenticated routes, RU/EN, widths 320/390/768/1440. Each page has a VEYRA title, a loaded visible shared mark, favicon metadata, no visible old brand, and no horizontal document overflow. The installed-app manifest name and real 192/512 PNG dimensions are checked. Desktop guest and mobile administration screenshots were visually inspected. JavaScript exception collection is empty. These are browser-emulation checks; actual phone installation caches remain dependent on the device.

## Follow-up: native admin section translations — 2026-10-24

The app index still exposed the technical app label `Hi` and Django's autogenerated English names for Company, Stat, CompanyValue, TeamMember, and HistoryItem. Added a lazy translated app display name (Медиаколлекция / Media collection), explicit singular/plural model labels, and translated form-field labels for those five models. English Companies replaces the autogenerated Companys. Admin lists retain Django's normal alphabetical sorting in the selected language, so their order can differ between RU and EN. URL namespaces, app labels, database table names, and stored user content remain unchanged.

Validation: 117 Django tests pass, including a regression test for the app index and all five add forms in both languages. Chromium checks 44 combinations (app index and five model lists/add forms, RU/EN, widths 390/1440) with no horizontal overflow or JavaScript exceptions. The Russian app-index screenshot was visually inspected. Migration 0013 contains only model/field presentation metadata; `sqlmigrate` emits no data/schema SQL. Run migrations after pulling to record the metadata migration.


## Follow-up: focused administration navigation — 2026-10-24

Added a supported AdminConfig/AdminSite subclass and removed the old admin-index monkey patch. The native index and collection app index now prioritize publications, comments and users in a stable bilingual order. Permission-filtered ratings/profiles/groups remain visible below; all ten portfolio/company/team models remain at their original URLs inside a default-closed additional group. Native content fills the available width, primary cards have larger targets, tables have more spacing, and the existing resumable uploader is the prominent action. The editorial dashboard remains at `/dashboard/` and retains the original publication form as a secondary option. The All sections link targets the permission-neutral admin index so staff managing only user accounts are not sent to a forbidden collection app index.

Renamed media presentation metadata to Publication/Publications and Publication title; migration 0014 produces no schema/data SQL. Review also found CompanyAdmin/DeveloperAdmin add overrides that checked only record count, bypassing model add permission. Both now require the inherited permission check plus the existing singleton condition.

Validation: 120 Django tests pass, including three new tests for stable grouped navigation, preserved legacy screens, read-only staff, add-only staff, upload visibility, and denied unauthorized company/developer creation. Bilingual form/index translation checks remain passing. Chromium checks 88 route/language/viewport combinations (eleven admin/dashboard/upload routes × RU/EN × 320/390/768/1440), primary ordering, default-closed legacy groups, keyboard disclosure activation, primary/CTA navigation, and limited-staff access. JavaScript exception collection is empty; desktop and mobile layouts were visually inspected. System checks, catalog checks, static collection and migration consistency pass. User accounts, publication bytes, and existing permission codenames remain unchanged.

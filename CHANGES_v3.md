# v3 changes

1. **Nothing is lost when you switch pages** (AI Engine + Donate): description, photos/videos, AI result,
   chosen NGO and the donation-confirmed card are kept (IndexedDB) until you press **New**.
   Leaving mid-analysis is safe: the server finishes and saves it; the page recovers it on return.
2. **Analyzed items go to My Items automatically** and are tracked: a timeline (Added -> AI analyzed -> Listed ->
   Donated ...), AI recommendation/score badges, CO2/resale, and a status dropdown. Listing on the marketplace
   or donating updates the status by itself (and the dashboard lifecycle counts).
3. **Donate page AI works**: description and/or photos and/or a My Items pick -> real AI analysis -> category +
   NGO matching. Clear inline errors; quick keyword matcher as fallback. Improved `/donate/classify`.
4. **After donating you get the NGO's contact details**: phone (Call / WhatsApp / Copy), address + Directions,
   email; also in My Donations ("Contact details"). Donations are now saved (new `DonationRecord`).
5. Fixes: My Items "Add Product" was broken (missing price/weight fields); pledge success threw an error after
   saving; donation errors no longer show a fake success.

Existing databases upgrade automatically on start (new product columns + new tables). No manual migration.
New endpoints: POST /products/from-analysis, GET /products/by-analysis/<ref>, GET /products/<id>/events,
GET /donate/my-donations, POST /donate/donations/<id>/cancel.

6. **Map search** now searches around your current location (10 km, then 30, then 80 km) instead of worldwide,
   asks for location first if needed, sorts by distance and zooms to the nearest results.

/* Headline-first editorial ranking. No invented press mentions or attendance figures.
   Major institutions and London-wide headline programmes lead; preferences refine.
   Browser global and Node exports share the identical scoring implementation. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CultureRanking = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const flagship = [
    /\btate modern\b/i, /\btate britain\b/i, /\bbritish museum\b/i,
    /\bv&a\b/i, /\bvictoria and albert museum\b/i, /\bnational gallery\b/i,
    /\broyal academy\b/i, /\bbarbican\b/i, /\bsouthbank centre\b/i,
    /\bhayward gallery\b/i, /\bnational theatre\b/i,
    /\broyal opera house\b/i, /\broyal ballet and opera\b/i,
    /\bsadler'?s wells\b/i, /\bserpentine\b/i,
    /\bscience museum\b/i, /\bnatural history museum\b/i,
    /\bimperial war museum\b/i, /\bdesign museum\b/i,
    /\bfrieze\b/i, /\bwellcome collection\b/i,
    /\broyal festival hall\b/i
  ];
  const significant = [
    /\byoung v&a\b/i, /\bcourtauld\b/i, /\bwhitechapel gallery\b/i,
    /\blondon museum\b/i, /\bwigmore hall\b/i, /\bold vic\b/i,
    /\byoung vic\b/i, /\broyal albert hall\b/i, /\bsomerset house\b/i,
    /\bwallace collection\b/i, /\bshakespeare'?s globe\b/i,
    /\bv&a east\b/i, /\bsouthbank\b/i, /\bkew gardens\b/i,
    /\bhorniman\b/i, /\bsaatchi gallery\b/i
  ];
  const majorTitle = /\b(retrospective|world premiere|uk premiere|london premiere|international festival|biennale|triennial|major exhibition|landmark exhibition|frieze london|frieze masters|turner prize)\b/i;
  const institutionSpecific = /\b(tate|barbican|royal opera|frieze|v&a|national theatre)\b/i;
  function venueTier(event) {
    const venue = String(event.venue || "");
    const title = String(event.title || "");
    if (flagship.some(rx => rx.test(venue))) return 3;
    if (significant.some(rx => rx.test(venue))) return 2;
    if (/frieze (london|masters|sculpture)/i.test(title)) return 3;
    if (institutionSpecific.test(title) && /(?:exhibition|production|festival)/i.test(title)) return 2;
    return 0;
  }
  function importance(event) {
    const tier = venueTier(event);
    const title = String(event.title || "");
    const desc = String(event.description || "");
    const source = String(event.source_type || "");
    let score = 10 + (tier === 3 ? 66 : tier === 2 ? 43 : 0);
    // Editorial cues add a smaller, evidence-based signal; generic adjectives
    // alone should never outperform a major institution.
    if (majorTitle.test(title)) score += 11;
    else if (majorTitle.test(desc)) score += 5;
    if (source === "official_event_page" || source === "event_jsonld" ||
        source === "official_venue_site") score += 5;
    if (Array.isArray(event.editorial_sources)) {
      const unique = new Set(event.editorial_sources.filter(u => /^https:\/\//.test(String(u))));
      score += Math.min(9, unique.size * 3);
    }
    if (event.venue === "London exhibition — see listing" ||
        event.venue === "London venue — confirm location") score -= 12;
    return Math.max(0, Math.min(100, score));
  }
  function preference(event, settings) {
    settings = settings || {};
    const interest = settings.interest || "balanced";
    let points = 0;
    if (interest === "art" && event.category === "art") points += 5;
    if (interest === "performance" && event.category === "performance") points += 5;
    if (interest === "family" && event.family_friendly) points += 7;
    if (event.family_friendly) points += Math.min(5, Math.max(0, Number(settings.familyBoost || 0) / 6));
    const venue = String(event.venue || "").toLowerCase();
    for (const token of String(settings.venues || "").split(",").map(x => x.trim().toLowerCase()).filter(x => x.length >= 3)) {
      if (venue.includes(token)) { points += 5; break; }
    }
    const searchable = (String(event.title || "") + " " + String(event.description || "")).toLowerCase();
    for (const token of String(settings.keywords || "").split(",").map(x => x.trim().toLowerCase()).filter(x => x.length >= 3)) {
      if (searchable.includes(token)) { points += 5; break; }
    }
    return Math.min(15, points);
  }
  function score(event, settings, today) {
    const prominent = importance(event);
    const personal = preference(event, settings);
    let time = 0;
    if (event.end_date && today) {
      const remaining = Math.round((Date.parse(event.end_date + "T12:00:00Z") - Date.parse(today + "T12:00:00Z"))/86400000);
      if (remaining >= 0 && remaining <= 4) time = 3;
    }
    // Minor proximity influence; missing journey estimates must not be fabricated.
    const travel = Number(event.travel_minutes_estimate);
    const proximity = Number.isFinite(travel) && travel > 0 && travel < 35 ? 2 : 0;
    return prominent + personal + time + proximity;
  }
  function select(events, settings, today, maximum) {
    const sorted = [...events].sort((a,b) => score(b,settings,today)-score(a,settings,today) ||
      String(a.title || "").localeCompare(String(b.title || "")));
    const output = [], counts = {};
    for (const event of sorted) {
      const key = String(event.venue || "").toLowerCase().trim();
      if ((counts[key] || 0) >= 2) continue;
      output.push(event);
      counts[key] = (counts[key] || 0) + 1;
      if (output.length === maximum) break;
    }
    return output;
  }
  return {score,importance,preference,venueTier,select};
});

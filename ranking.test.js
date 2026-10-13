const assert=require('node:assert/strict');
const test=require('node:test');
const rank=require('./ranking.js');
const base={start_date:'2026-10-01',end_date:'2026-11-30',category:'art',source_type:'date_calendar:IanVisits'};
test('headline exhibition at Tate outranks small independent gallery',()=>{
 const major={...base,title:'Ana Mendieta',venue:'Tate Modern'};
 const niche={...base,title:'The Unclassified',venue:'Korean Cultural Centre UK'};
 assert.ok(rank.score(major,{},'2026-10-13')>rank.score(niche,{},'2026-10-13')+45);
});
test('large programme outranks a keyword-stuffed niche listing',()=>{
 const major={...base,title:'The 90s: Art and Fashion',venue:'Tate Britain'};
 const niche={...base,title:'Immersive contemporary modern art installation exhibition digital art immersive',venue:'Small Gallery',score:500};
 assert.ok(rank.score(major,{},'2026-10-13')>rank.score(niche,{interest:'art',keywords:'immersive'},'2026-10-13'));
});
test('custom interests refine but do not override headline prominence',()=>{
 const major={...base,title:'Schiaparelli',venue:'V&A South Kensington'};
 const niche={...base,title:'Small art photography exhibition',venue:'Local Project Room'};
 assert.ok(rank.score(major,{venues:'Local Project Room',keywords:'photography',familyBoost:30},'2026-10-13')>rank.score(niche,{venues:'Local Project Room',keywords:'photography',familyBoost:30},'2026-10-13'));
});
test('family relevance boosts a major family event',()=>{
 const family={...base,title:'Inside Aardman',venue:'Young V&A',family_friendly:true,category:'family'};
 const adult={...base,title:'Small Exhibition',venue:'Indie Project Room',family_friendly:false};
 assert.ok(rank.score(family,{interest:'family',familyBoost:30},'2026-10-13')>rank.score(adult,{interest:'family'},'2026-10-13'));
});
test('news coverage only counts when supplied as actual source URLs',()=>{
 const major={...base,title:'Exhibition',venue:'Somerset House'};
 const baseline=rank.importance(major);
 assert.equal(rank.importance({...major,editorial_mentions:500}),baseline);
 assert.ok(rank.importance({...major,editorial_sources:['https://example.com/a']})>baseline);
});
test('top twenty selects higher importance first with venue diversity',()=>{
 const events=[...Array(25)].map((_,i)=>({...base,title:'Local Show '+i,venue:'Independent '+i}));
 events.push({...base,title:'Major Exhibit',venue:'National Gallery'});
 const items=rank.select(events,{},'2026-10-13',20);
 assert.equal(items.length,20);
 assert.equal(items[0].title,'Major Exhibit');
});

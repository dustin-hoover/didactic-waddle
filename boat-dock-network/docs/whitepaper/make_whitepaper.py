#!/usr/bin/env python3
"""Boat Dock Network white paper -> docs/whitepaper/white_paper.html (living artifact).

Version 1 is generated from the plan (docs 01-24, the models and test results). After it
is published, the page itself is the master copy: writers edit sections and record
decisions in place, and each save becomes a new version (artifact capability). To make
a later edit from code, read the published page back first and build on that version.
Run: python3 docs/whitepaper/make_whitepaper.py
"""
import os, json, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
M = json.load(open(os.path.join(REPO, "data", "financial", "model_summary.json")))
SP = json.load(open(os.path.join(REPO, "data", "noc", "spof_report.json")))

def k(v):   # $000 -> $x.xM / $xxxk
    return f"${v/1000:.1f}M" if abs(v) >= 1000 else f"${v:,.0f}k"

def tbl(head, rows, num=(), total=False):
    th = "".join(f'<th class="n">{h}</th>' if i in num else f"<th>{h}</th>" for i, h in enumerate(head))
    trs = []
    for j, r in enumerate(rows):
        cls = ' class="total"' if total and j == len(rows) - 1 else ""
        trs.append(f"<tr{cls}>" + "".join(f'<td class="n">{c}</td>' if i in num else f"<td>{c}</td>" for i, c in enumerate(r)) + "</tr>")
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'

Y = ["1", "2", "3", "4", "5"]
def row(label, key, neg=False):
    return [label] + [(f'<span class="neg">({abs(M[key][y]):,})</span>' if M[key][y] < 0 else f"{M[key][y]:,}") for y in Y]

import csv
pf = {r["line_item"]: r for r in csv.DictReader(open(os.path.join(REPO, "data", "financial", "pro_forma.csv")))}
def pfrow(label, key, pct=False):
    out = [label]
    for y in ("Y1", "Y2", "Y3", "Y4", "Y5"):
        v = float(pf[key][y])
        out.append(f"{v:.0%}" if pct else (f'<span class="neg">({abs(v):,.0f})</span>' if v < 0 else f"{v:,.0f}"))
    return out

S = []
def sec(id_, title, html):
    S.append({"id": id_, "num": f"{len(S):02d}" if S else "ES", "title": title, "html": html.strip()})

# ------------------------------------------------------------------------------ ES
sec("summary", "Executive summary", f"""
<p><strong>Boat Dock Network (BDN)</strong> is a planned member-owned cooperative internet provider for the whole shoreline of Beaver Lake in Northwest Arkansas. It combines fiber where homes are close together with fixed wireless where trees and terrain make fiber uneconomic, and it uses the lake itself as its right-of-way and, where it's faster, its road. Members own it, govern it through a tenure-earned vote that can't be bought, and share its surplus through patronage dividends. The base case uses <strong>no government grants or government loans</strong>.</p>
<div class="figs">
<div><b>9,571</b><span>premises within 1 mile of the shore (verified from county parcels)</span></div>
<div><b>{M['subs_year5']:,}</b><span>members by Year 5 at a 44% take rate</span></div>
<div><b>{k(M['capex_5y_000'])}</b><span>five-year capital cost, including $300k of land</span></div>
<div><b>{k(M['peak_funding_need_000'])}</b><span>peak funding need before cash turns positive</span></div>
<div><b>${M['cost_per_passing']}</b><span>cost per premises passed (fiber overbuild ≈ $1,800)</span></div>
<div><b>Year {M['ebitda_positive_year']}</b><span>EBITDA-positive; cash-positive about Year {M['cash_positive_year']}</span></div>
</div>
<h3>What the plan rests on</h3>
<ul>
<li><strong>Verified geography, not estimates.</strong> Premises, zones, node sites and line of sight come from county parcels, USGS lake data and LiDAR. The LiDAR check showed real tree canopy blocks about half the clean wireless paths a simpler model predicted, so the design uses taller towers (30–45 m) and non-line-of-sight radios.</li>
<li><strong>A hybrid network.</strong> Two diverse internet on-ramps, a backbone around and across the lake, 30 dock and relay nodes, and per-address choice of fiber or wireless.</li>
<li><strong>Cooperative ownership.</strong> Governance (the non-transferable WAKE unit) is kept separate from money (patronage dividends), and capital never buys votes.</li>
<li><strong>Grant-free funding.</strong> Founder equity, member capital, per-zone pre-sales, cooperative and commercial debt, and equipment finance. Each zone is built only when its own residents have reserved and committed capital.</li>
<li><strong>DockOS, the operating software, is already largely built and tested.</strong> Serviceability and signup, member capital, governance voting, billing with RADIUS, work orders and boat/truck dispatch with a crew app, and a network operations center that finds root causes and credits members automatically.</li>
</ul>
<h3>What testing changed</h3>
<p>Building and testing the plan against real data overturned three assumptions, and the plan now reflects each:</p>
<ol>
<li><strong>"The lake is the road" is true for about a quarter of premises, not all.</strong> Against real roads, a boat beats a truck for 24% of premises at a 15-minute dock turnaround and 52% at 5 minutes. The field fleet is therefore hybrid, and dock turnaround is the key operating number.</li>
<li><strong>The backbone "ring" is not a ring yet.</strong> 56% of Year-5 members sit behind a single point of failure. Five added links ($40k if radio paths are clear, up to $689k as fiber) remove most of that risk.</li>
<li><strong>Weather affects wireless members differently from fiber members.</strong> Rain barely touches the bands used to reach homes, but storms still interrupt service through wet foliage, static and power blips. Three short backbone crossings are planned on a band heavy rain would knock out. Wireless members need to be told this before they sign up.</li>
</ol>
<p>This paper is a <strong>working draft</strong>. Twenty decisions remain open (see the register at the end). The plan is final when they're resolved.</p>
""")

# ------------------------------------------------------------------------------ 1
sec("opportunity", "The opportunity: Beaver Lake", """
<p>Beaver Lake is a U.S. Army Corps of Engineers reservoir on the White River: <strong>28,026 acres</strong> of water and <strong>445 miles</strong> of shoreline (both measured from the USGS lake polygon), across Benton, Washington and Carroll counties. Its shape is a long main channel with dozens of branching coves. That shape is why incumbents, who build along town roads, leave so much of the shoreline thinly served, and why a zoned, lake-aware network fits.</p>
<h3>Who is there</h3>
""" + tbl(["Measure", "Value", "Source"], [
    ["Premises within 1 mile of shore", "9,571", "County parcels with improvements (AR GIS Office)"],
    ["Premises within ¼ mile", "6,144", "Same"],
    ["By county (≤ 1 mile)", "Benton 7,190 · Washington 1,318 · Carroll 1,044 · Madison 19", "Same"],
    ["Vacant shoreline parcels (≤ ¼ mile)", "5,943", "Growth and host-site land"],
    ["Year-round vs seasonal homes", "55% / 45% (estimate, not yet verified)", "Homestead flags still to pull"],
]) + """
<h3>Demand and competition</h3>
<ul>
<li><strong>Demand:</strong> remote work, second homes and vacation rentals, and marinas and resorts that need dependable connectivity. Lakeshore owners skew toward higher incomes and value reliability and local service over price.</li>
<li><strong>Competition:</strong> Cox, Sparklight, AT&amp;T, cooperative fiber (OzarksGo, Carroll Electric) and Starlink. They are strong in town and thin in the coves; the coves are BDN's opening.</li>
</ul>
<h3>Zones and build order</h3>
<p>GIS analysis divided the shoreline into <strong>18 service zones</strong> (Z-01 to Z-18) and ranked <strong>30 candidate node sites</strong> by what they can see. Six nodes cover 60% of premises and all 30 cover 84%. The recommended first phase is <strong>Prairie Creek, Beaver Shores and Monte Ne</strong>, the densest part of the Benton County corridor.</p>
""")

# ------------------------------------------------------------------------------ 2
sec("cooperative", "The model: a member-owned cooperative", """
<p>BDN is designed as a <strong>member cooperative</strong>: the people it serves own and govern it. Two separate rails keep that simple and legally safe.</p>
""" + tbl(["Rail", "Vehicle", "Who gets it", "Legal nature"], [
    ["Governance", "WAKE units (non-transferable)", "Earned by membership tenure", "Not a security: no price, can't be traded, no profit expectation"],
    ["Economics", "Patronage dividends (cash or bill credit)", "Allocated by service purchased", "Established cooperative mechanism (Subchapter T)"],
]) + """
<h3>How WAKE works</h3>
<ul>
<li>Every active member earns <strong>1 WAKE per month</strong>; members who host a network node earn <strong>1.5×</strong>.</li>
<li>A vote weighs <strong>1 + WAKE</strong>, capped at <strong>120</strong> (about ten years), so early members can't entrench permanently.</li>
<li><strong>Anti-capture:</strong> no single member's vote may exceed the greater of 2% of the total or one equal share. The rule holds at any membership size and is unit-tested from 2 to 4,000 members.</li>
<li>Members who leave <strong>forfeit</strong> their WAKE to a Commons Pool; half the pool is redistributed to active members each year. A <strong>seasonal hold keeps membership and accrual</strong>, so lake residents don't lose their voice every winter.</li>
<li>Simulated over eight years, the founding cohort's share of the vote falls from 100% to about <strong>11%</strong>: the co-op decentralizes as it grows.</li>
</ul>
<h3>Capital never buys votes</h3>
<p>Membership shares, deposits and founding capital (section 13) are financial instruments only. Founding members may receive recognition and a one-time, capped WAKE grant; that's an open decision. Governance stays tenure-earned. WAKE lives in DockOS's own ledger first; an on-chain mirror is optional later, and <strong>there will never be a token sale or tradable market</strong>.</p>
<h3>What members vote on</h3>
<p>Board seats, bylaw changes, patronage policy, which zones to build next, and major capital decisions. A working voting portal (proposals, tenure-weighted and capped voting, quorum) already exists.</p>
<blockquote><p>Securities and cooperative counsel must review the instruments and the WAKE design before launch. The design is deliberately shaped to make that review straightforward.</p></blockquote>
""")

# ------------------------------------------------------------------------------ 3
sec("network", "Network design", """
<p>In one sentence: <strong>two diverse internet on-ramps feed a backbone around and across the lake (licensed microwave over water, fiber or radio on land), which feeds zoned dock and relay nodes that serve each address by fiber or wireless, whichever fits.</strong></p>
<h3>The tiers</h3>
""" + tbl(["Tier", "Role", "Equipment class", "Power"], [
    ["T0 head-end (×2)", "Internet on-ramp, border routing, core", "Border router, DWDM, core switching, CGNAT/DNS", "Grid + generator + UPS"],
    ["T1 core", "Backbone transport and aggregation on high ground", "Licensed microwave, aggregation router, optional fiber head (OLT)", "Grid + UPS (4–8 h)"],
    ["T2 dock node (18)", "Serves a zone from a high shoreline point", "Access radios (sectors), optional fiber splitters, backhaul radio", "Grid + UPS"],
    ["T3 relay (12)", "Fills radio shadows and extends reach", "Relay radios", "Solar + LiFePO4, 2–3 days' autonomy"],
    ["T4 premises", "The member's home or business", "Wireless receiver or fiber terminal, Wi-Fi router", "Member's power"],
]) + """
<h3>Choosing fiber or wireless per address</h3>
<ol>
<li><strong>Fiber</strong> where homes are dense, where a business or marina needs it, or where a host site justifies it.</li>
<li><strong>Non-line-of-sight wireless</strong> (Tarana-class radios on shared CBRS spectrum at 3.55–3.7 GHz, or 6 GHz) for tree-shadowed homes.</li>
<li><strong>Line-of-sight wireless</strong> (Cambium or Ubiquiti 5/6 GHz sectors) for clear clusters and marinas.</li>
<li>A relay or fiber extension where none of those reaches.</li>
</ol>
<h3>Backbone</h3>
<p>The designed backbone has <strong>41 links costing about $1.37M</strong>: 22 long lake crossings on licensed microwave with two dishes for diversity over water, 3 short lake hops, and 16 land hops. Long crossings target 99.999% availability per hop, with fade margins that account for the lake's seasonal level changes.</p>
<h3>Addressing and routing</h3>
<ul>
<li>BDN's own ARIN AS number and IPv6 space (a /36, split into a /40 per region, a /44 per zone and a /56 per member), plus an IPv4 /24 through the waitlist with leased space as a bridge; carrier-grade NAT only as a stopgap.</li>
<li>BGP to both upstreams; IS-IS inside; an SR-MPLS or EVPN overlay for per-zone separation once zones grow.</li>
<li>RPKI route signing and validation, MANRS practices, BCP38 anti-spoofing, DDoS support written into the transit request.</li>
</ul>
<h3>Standards</h3>
<p>XGS-PON (ITU-T G.9807.1) for fiber; FCC Part 96 (CBRS), Part 15 (unlicensed) and Part 101 (licensed microwave); NEC 800/810 and Motorola R56 grounding; NEMA-4X enclosures. Equipment is specified by class, not brand, so electronics can be swapped as technology improves. The full engineering spec is doc 21.</p>
""")

# ------------------------------------------------------------------------------ 4
sec("coverage", "Coverage: what the GIS and LiDAR showed", """
<p>Every coverage number in this plan comes from real spatial data, analysed in PostGIS.</p>
<ul>
<li><strong>Canopy-aware viewshed</strong> (bare-earth elevation plus the national land-cover canopy layer): 75% of premises (7,154) are reachable by line-of-sight wireless and 25% (2,417) sit in radio shadow and need a relay or fiber. On bare earth alone the figure would be 87%.</li>
<li><strong>LiDAR validation.</strong> A true surface model built from 3DEP LiDAR point clouds found real canopy blocks much more than the land-cover layer suggests: in Phase 1 zones, clean line of sight at short masts was <strong>26%, not 44%</strong>.</li>
<li><strong>The engineering answer:</strong> 30–45 m towers (recovering line of sight to about 40–45%), non-line-of-sight radios for the rest, and more relays and fiber. The financial model was rebuilt on this LiDAR-informed base case. That's why capital cost is $8.6M rather than the earlier $7.5M.</li>
</ul>
<p>Outputs you can inspect: the zone and node tables, the build-order ranking, the LiDAR validation table, and the interactive <a href="https://claude.ai/artifact/L4Jq482X74PeXJkWBL71cS">Beaver Lake Network Map</a>.</p>
""")

# ------------------------------------------------------------------------------ 5
spofs = SP["before"]["spofs"]
sec("reliability", "Reliability: the ring audit", f"""
<p>The early plan called the backbone "a ring, so any one break heals." When the network operations software was tested against the designed topology, it showed <strong>the backbone is not yet a ring</strong>. It is a tree with a few loops.</p>
<div class="flag"><p><strong>{SP['before']['bridges']} links and {SP['before']['cut_nodes']} sites are single points of failure.</strong> {SP['before']['members_behind_a_spof']:,} of {SP['members_total']:,} Year-5 members (56%) sit behind at least one. The worst, land hop SP-06-13, carries 2,243 members, half the network. The northwest head-end connects only to the site at that link's end.</p></div>
""" + tbl(["Single point of failure", "Kind", "Sites cut off", "Members behind it"], [
    [r["element"], (r["kind"].replace("_", " ") + " link") if r["type"] == "link" else (r["kind"] + " site"), len(r["isolates_nodes"]), f"{r['members']:,}"] for r in spofs
], num=(2, 3)) + f"""
<h3>The fix: close the ring</h3>
<p>A planner added, one at a time, the cheapest link (within 7 km) that removes the worst remaining weak point:</p>
""" + tbl(["#", "Removes", "Adds a link between", "km", "As radio", "If it must be fiber"], [
    [i + 1, a["removes_spof"], f"{a['add_hop']['a']} ↔ {a['add_hop']['b']}", a["add_hop"]["km"], f"${a['add_hop']['cost_radio_or_class']:,}", f"${a['add_hop']['cost_if_aerial_fiber']:,}"]
    for i, a in enumerate(x for x in SP["plan"]["added"] if x.get("add_hop"))
] + [["", "", "Total", "", f"${SP['plan']['total_cost_low']:,}", f"${SP['plan']['total_cost_high']:,}"]], num=(3, 4, 5), total=True) + f"""
<p>Afterwards there are no bridge links, and members behind a single point of failure drop from {SP['before']['members_behind_a_spof']:,} to <strong>{SP['after']['members_behind_a_spof']:,}</strong>. Two sites remain weak points (BDN-Z-10-N11 with 429 members and BDN-Z-16-N05 with 124), because neither has another site within 7 km. Each needs a new relay site or a dual-radio node with a hot spare.</p>
<h3>Recommendation</h3>
<ol>
<li>Survey the five paths with LiDAR before buying backbone equipment. Radio prices assume clear paths, and canopy blocks about half.</li>
<li>Budget $40k, and move individual links to licensed microwave or fiber only where the survey fails.</li>
<li>Give the northwest head-end a second connection.</li>
</ol>
<p>The financial model does not yet include this cost; that's an open decision. The weak points are also visible on the <a href="https://claude.ai/artifact/XTgZQdX7AoB6URdGadwsNX">DockOS NOC board</a>.</p>
""")

# ------------------------------------------------------------------------------ 6
sec("weather", "Weather and wireless service", """
<p>Fiber members and wireless members will have different experiences in storms, and this plan says so plainly.</p>
<h3>How much rain actually costs each band</h3>
<p>Using the ITU rain models for Beaver Lake, a heavy storm (about 48 mm per hour, the rate exceeded roughly 53 minutes a year) weakens a 2 km radio link by:</p>
""" + tbl(["Band", "Used for", "Signal lost over 2 km", "Effect"], [
    ["3.6 GHz (CBRS)", "Non-line-of-sight radios to tree-shadowed homes", "0.06 dB", "None"],
    ["5–6 GHz", "Line-of-sight radios to homes", "0.5–0.9 dB", "Small"],
    ["11 GHz", "Licensed long lake crossings", "about 4 dB", "Designed for"],
    ["23 GHz", "Licensed short hops", "about 13 dB", "Needs margin"],
    ["60 GHz", "Short unlicensed backhaul", "about 33 dB", "Link drops"],
], num=(2,)) + """
<h3>Why storms still interrupt home wireless</h3>
<p>Home links are designed with at least 10 dB of spare signal, so on the bands BDN uses to reach homes, rain alone shouldn't drop them. Storm outages usually come from rain-soaked leaves in the path, water in cable connectors, static from nearby lightning that locks up a radio or router, or a power blip at the house or the tower. Needing to reset equipment after a storm points to that lock-up, and that part is fixable.</p>
<h3>What BDN will do about it</h3>
<ul>
<li><strong>Self-recovering equipment.</strong> Radios run a connection watchdog (Ubiquiti calls it Ping Watchdog) that restarts the radio automatically, and the network operations center can restart any member radio remotely.</li>
<li><strong>Surge standard on every install.</strong> A surge protector at the antenna and at the building entry, shielded cable, and proper grounding. Nothing protects against a direct lightning strike.</li>
<li><strong>No bare 60 GHz where it matters.</strong> 60 GHz is used only on very short links, and only with a built-in 5 GHz backup such as airFiber 60 LR or 60 XG, tested before relying on it.</li>
<li><strong>Storm handling in operations:</strong> recognize storm-wide drops, restart what hasn't recovered after the storm, send one notice, and send a crew to any install that drops in every storm.</li>
</ul>
<div class="flag"><p><strong>Design issue to fix before buying equipment:</strong> three short lake crossings (2.3–2.6 km) are planned as "unlicensed 60 or 5 GHz." At 60 GHz, heavy rain adds about 40 dB of loss and moderate rain about 25 dB, which would drop them and, with the ring not yet closed, could take whole zones down. They should be 5/6 GHz, 60 GHz with 5 GHz backup, or licensed 18/23 GHz.</p></div>
<h3>What wireless members will be told</h3>
<blockquote><p>Fixed-wireless service reaches your home by radio from a nearby network site. Heavy rain, wet leaves and nearby lightning can briefly interrupt it, usually for a few minutes while a storm passes. Your equipment is set to recover on its own, and we can restart it remotely. If service isn't back 15 minutes after the storm passes, unplug the outdoor antenna's power adapter for 30 seconds, plug it back in, then restart your router. Short weather interruptions aren't covered by outage credits; outages of 24 hours or more are.</p></blockquote>
<p>Wireless applicants would acknowledge this at signup, and it would go in the member agreement. What BDN asks of wireless members is small: keep the router and antenna adapter on a surge strip (ideally a small battery backup), and know the one-step reset.</p>
<div class="proposed"><p><strong>Status:</strong> proposed, not yet built. The disclosure in the signup portal, the storm mode in operations and the wireless equipment spec are the next items once approved.</p></div>
""")

# ------------------------------------------------------------------------------ 7
sec("transit", "Internet transit and middle-mile", """
<p>BDN buys two things: <strong>transport</strong> from a carrier's point of presence to each head-end, and <strong>IP transit</strong>, the route to the internet. The two paths must be physically separate so one cut can't darken the lake.</p>
<p><strong>Key finding:</strong> Diamond State Networks, a wholesale middle-mile network formed by 13 Arkansas electric cooperatives including OzarksGo, already sells exactly this, over 50,000+ route-miles. It is the lead candidate for path A, co-op to co-op. Path B goes to a physically diverse second carrier chosen by RFQ (candidates: Uniti, Lumen, Cox Business, Aristotle, AT&amp;T Wholesale).</p>
""" + tbl(["Year", "Members", "Peak (Gbps)", "Provisioned (Gbps)", "Ports per path", "Est. cost/yr"], [
    ["Y1", "835", "2.7", "3.8", "10G ×2", "~$58k"], ["Y2", "1,889", "6.9", "9.6", "10G ×2", "~$92k"],
    ["Y3", "2,963", "12.3", "17.3", "25G ×2", "~$127k"], ["Y4", "3,828", "17.9", "25.1", "25G ×2", "~$157k"],
    ["Y5", "4,211", "21.9", "30.7", "100G ×2", "~$213k"],
], num=(1, 2, 3, 5)) + """
<p>The RFQ, provider outreach list, provider scorecard, ARIN resource request and a four-layer path-diversity acceptance test are packaged and ready to send. What remains needs a person: forming the entity (which ARIN requires), confirming exact POP sites, and sending the RFQ.</p>
""")

# ------------------------------------------------------------------------------ 8
sec("sites", "Sites and real estate", """
<p><strong>Own the two head-end sites outright; lease or take recorded easements for everything else.</strong></p>
""" + tbl(["Site", "What it is", "Own, lease or easement", "Why"], [
    ["T0 head-end ×2", "Internet on-ramp and core equipment", "Buy (fee simple)", "Permanent control; collateral for co-op debt; no eviction or rent-escalation risk"],
    ["T1 core", "Ridge-top backbone sites", "Long ground lease (10–25 yr), or buy if strategic", "Control without full capital"],
    ["T2/T3 edge (~30)", "Dishes and cabinets on high points and member docks", "Recorded easement or member host", "Cheap and fast; hosts earn 1.5× WAKE and a service credit"],
]) + """
<ul>
<li><strong>Enclosures:</strong> a walk-in shelter only where a head-end's equipment density justifies it; pad-mounted outdoor cabinets for most T0/T1 and dense T2 sites; small pole-mounted cabinets for edge nodes and relays.</li>
<li><strong>A good head-end parcel</strong> has a short fiber lateral to a carrier, a route diverse from the other head-end, commercial power with generator room, height for lake crossings, both road and boat access, and clean zoning outside restricted Corps shoreline.</li>
<li><strong>Money:</strong> the model carries $150k of land for each head-end ($300k total). Owned land and equipment give a collateral base of about $2.2M.</li>
<li><strong>Legal wrapper for each purchase:</strong> title and survey, zoning or conditional use, FAA review for towers, Corps review near the shoreline, Phase I environmental, and floodplain checks.</li>
</ul>
<p>A lakeside head-end parcel could also be the boat and operations base. Whether to combine them is an open decision.</p>
""")

# ------------------------------------------------------------------------------ 9
sec("operations", "Operations: boat-native, and measured", """
<p>Field work (builds, installs and repairs) is dispatched by software, with crews on boats or trucks. The plan originally assumed the boat would always be faster. It was tested against the real lake and the real road network.</p>
<div class="figs"><div><b>24%</b><span>of premises where a boat beats a truck, at 15 min per dock stop</span></div><div><b>52%</b><span>at 5 min per dock stop</span></div><div><b>1,905</b><span>premises in five boat-first zones</span></div><div><b>5,514</b><span>premises in eight truck-first zones</span></div></div>
<p><strong>What decides it is the time each dock stop takes</strong> (tie up, unload, walk up), not boat speed or the number of yards. The plan therefore runs a <strong>hybrid fleet</strong>:</p>
<ul>
<li>Boats own the boat-first arms (Lost Bridge, Township of Prairie, Huffman Ford, Vista Shores, Ventris) and all waterside work: dock nodes, lake crossings, underwater cable and shoreline host sites.</li>
<li>Service trucks are primary in the truck-first zones, which include the three largest.</li>
<li>Dock turnaround of <strong>8 minutes or less</strong> is the key operating target. It's measured on every stop by the crew app, and the planner uses the measured figure once it has enough samples.</li>
</ul>
<h3>How a day works</h3>
<ul>
<li>A <strong>weather gate</strong> uses the National Weather Service hourly forecast: each boat class has its own wind limit (jon boat 15 mph, pontoon 20, center console 25), and thunderstorms keep boats in. Boat-only jobs wait; others go by truck. The dispatcher can override.</li>
<li>The planner assigns each job to the eligible crew where it adds the least travel, within the shift. An outage repair goes in as the <strong>next stop</strong> of whichever crew can get there first.</li>
<li>Crews use an <strong>offline-first phone app</strong>: run sheet, lake chart with routes, checklists, required readings, barcode scanning, and a queue that syncs when there's signal. Finishing an install starts the member's billing.</li>
</ul>
<h3>Safety</h3>
<p>Coast Guard-compliant vessels, float plans, a buddy system for mid-lake and mast work, lightning and wind stand-downs, fall protection, and zero-spill discipline near the Beaver Water District drinking-water source: sealed batteries, spill kits and no fueling over water.</p>
<h3>Seasonality</h3>
<p>Builds and installs peak spring to fall; winter is for hardening nodes, maintenance, design and permitting. Solar sites are sized for winter minimums.</p>
""")

# ------------------------------------------------------------------------------ 10
sec("dockos", "DockOS: the software that runs the co-op", """
<p>DockOS is one open-source-first system with PostGIS as the single source of truth for the network, the members, the money and the map. Seven of its eight modules are built and tested end to end against real services and data.</p>
""" + tbl(["#", "Module", "Status", "What it does"], [
    ["1–2", "PostGIS + GIS analysis", "Built", "Premises, zones, line of sight, viewshed, build order"],
    ["3", "Serviceability + signup portal", "Built", "Drop a pin, see if it's served, reserve, pledge; live <a href=\"https://claude.ai/artifact/LeEBTN21as8wm7EBQRtrpe\">signup portal</a>"],
    ["—", "Member capital + governance", "Built", "Pledges through Stripe; WAKE ledger and <a href=\"https://claude.ai/artifact/VdhypMHV8Z748GMJhgZiXK\">voting portal</a>"],
    ["4–5", "Work orders, dispatch, crew app", "Built · 43 checks", "Sign-up to install to first bill; <a href=\"https://claude.ai/artifact/5teoYVbPD7nKjV55wNN3KH\">DockOS Crew</a>"],
    ["6", "Billing, provisioning, RADIUS", "Built · 46 checks", "Tested against a live FreeRADIUS server"],
    ["7", "Network operations + outages", "Built · 52 checks", "Root cause, dispatch, notices, credits; <a href=\"https://claude.ai/artifact/XTgZQdX7AoB6URdGadwsNX\">DockOS NOC</a>"],
    ["8", "Compliance advisor", "Next", "Arkansas, county and federal obligations, tracked per work order"],
]) + """
<h3>Design choices worth knowing</h3>
<ul>
<li><strong>Billing state is network policy.</strong> The RADIUS tables that authorize members are database views over billing, so a suspension or plan change takes effect on the next connection with nothing to sync. Live sessions are updated immediately.</li>
<li><strong>Outages close on telemetry, not on a crew's word.</strong> The operations center turns an alarm storm into one root cause, tells affected members once, and credits them automatically.</li>
<li><strong>Offline-first field work.</strong> Every tap is queued with an ID and applied exactly once when signal returns.</li>
<li><strong>Everything is tested end to end</strong> on real data: 141 automated checks across the three operational suites.</li>
</ul>
""")

# ------------------------------------------------------------------------------ 11
sec("members", "The member experience", """
<h3>Plans and prices (planning)</h3>
""" + tbl(["Plan", "Speed (symmetric)", "Price/month"], [
    ["Cove", "300 Mbps", "$69"], ["Shoreline", "1 Gbps", "$89"], ["Deep Water", "2–5 Gbps (fiber where available)", "$129–$199"],
    ["Dock Business", "1 Gbps + static IP", "$199"], ["Marina Managed", "Multi-gig + managed slip Wi-Fi", "$399–$1,200"], ["Resort/Enterprise", "Custom + SLA", "Custom"],
], num=(2,)) + """
<p>No data caps. Add-ons: managed Wi-Fi, static IPs, voice, marina guest Wi-Fi, priority business service.</p>
<h3>Host a node</h3>
<p>Owners who host equipment get a service credit (about $25/month for a relay, $75/month or free Shoreline service for a dock node, free service plus a lease payment for a core site) and earn WAKE at 1.5×. This recruits the best sites while building loyalty and coverage.</p>
<h3>Joining and paying</h3>
<ul>
<li>Check an address, reserve with a refundable $100 deposit, and become a member with a $200 share.</li>
<li>After installation, the first bill is prorated, with the deposit credited against it.</li>
<li>Late payments: a reminder at 10 days, restricted access at 21 days, and termination at 60 days.</li>
<li><strong>Seasonal hold</strong> for lake homes: $10/month, and membership and WAKE continue.</li>
<li>Instant plan changes. Cancelling forfeits WAKE to the Commons Pool (a hold is offered instead).</li>
</ul>
<h3>When something breaks</h3>
<ul>
<li>Affected members get one text and email with an estimated restore time, and a "restored" notice afterwards.</li>
<li>A public status page shows each area's state with no personal data.</li>
<li><strong>Credits are automatic (proposed terms):</strong> businesses get twice the prorated time for any outage over 4 hours; residential members get whole days for outages of 24 hours or more. Both are capped at one month and applied to the next bill.</li>
<li>Members on seasonal hold aren't counted as down.</li>
</ul>
""")

# ------------------------------------------------------------------------------ 12
sec("financials", "Financial plan", f"""
<p>The base case is LiDAR-informed and grant-free. Figures are in thousands of dollars unless noted.</p>
""" + tbl(["", "Y1", "Y2", "Y3", "Y4", "Y5"], [
    pfrow("Premises passed", "premises_passed_cumulative"), pfrow("Members", "subscribers_cumulative"), pfrow("Take rate", "take_rate", pct=True),
    pfrow("Revenue", "revenue_total_$000s"), pfrow("Operating cost", "opex_total_$000s"), pfrow("EBITDA", "ebitda_$000s"),
    pfrow("Capital spending", "capex_total_$000s"), pfrow("Cash flow before financing", "cash_flow_pre_financing_$000s"),
    pfrow("Cumulative cash", "cash_flow_cumulative_$000s"),
], num=(1, 2, 3, 4, 5)) + f"""
<div class="figs"><div><b>{k(M['capex_5y_000'])}</b><span>5-year capital ({k(M['infra_5y_000'])} infrastructure, $300k land)</span></div><div><b>{k(M['peak_funding_need_000'])}</b><span>peak funding need</span></div><div><b>${M['cost_per_passing']}</b><span>per premises passed</span></div><div><b>${M['cost_per_sub']:,}</b><span>per member connected</span></div><div><b>${M['arpu_mo']}</b><span>average revenue per member per month</span></div><div><b>{k(M['collateral_base_000'])}</b><span>owned-asset collateral base</span></div></div>
<h3>Accounting principle</h3>
<p>Labor and materials that build the network are capitalized and depreciated; operating cost is only the team that runs the business. That's why EBITDA turns positive in Year 2 while cumulative cash doesn't until about Year 6.</p>
<h3>Not yet in the model</h3>
<ul>
<li>Closing the ring: $40k (radio) to $689k (all fiber).</li>
<li>A fleet re-cut toward service trucks and fewer, better-equipped boats.</li>
<li>Real transit quotes, which replace the planning estimates in section 7.</li>
<li>Any change from the three short lake crossings (section 6).</li>
</ul>
""")

# ------------------------------------------------------------------------------ 13
sec("funding", "Funding without grants", """
<p>The base case uses <strong>no BEAD, USDA, state grants or federal loans</strong>. Grants are optional upside only if the landscape changes, never a dependency.</p>
""" + tbl(["Source", "Role", "Indicative size"], [
    ["Founder / owner equity", "First-in risk capital: entity, GIS, pilot", "$0.75–1.25M"],
    ["Member capital", "The grant replacement: shares, founding capital, retained patronage", "$0.6–1.2M"],
    ["Pre-sales deposits", "Working capital per zone; gates each build", "Rolling"],
    ["Cooperative and commercial debt", "Most infrastructure (CoBank, RTFC/CFC, local banks)", "$1.0–2.0M"],
    ["Equipment financing / leasing", "Radios, fiber electronics, fleet", "$0.5–1.0M"],
    ["Anchor prepayments", "Marinas and resorts prepaying multi-year service", "Situational"],
], num=(2,)) + """
<h3>The member-capital campaign</h3>
""" + tbl(["Instrument", "Amount", "Refundable?", "Purpose"], [
    ["Membership share", "$200 once", "Yes, on exit", "Member-owner; starts WAKE accrual"],
    ["Reservation deposit", "$100", "Yes; credited to the first bill", "Reserves a spot, funds the zone, proves demand"],
    ["Founding-member capital", "$500 / $1,500 / $5,000", "Per terms (revolving member capital)", "Early risk capital from residents, marinas and resorts"],
]) + """
<p><strong>A zone is built only when both are true:</strong> reservations reach 25% of its premises, <em>and</em> committed capital reaches $75 per premises. Members vote with deposits, and BDN builds where the lake asks. The owner's campaign cockpit tracks each zone against its gate live. Deposits and founding capital sit in a segregated escrow account.</p>
<p>Lenders need three things: pre-sales traction per zone, a verified data room (GIS, cost per passing, pro forma, maps), and a credible team with clean co-op governance.</p>
""")

# ------------------------------------------------------------------------------ 14
sec("legal", "Legal, entity and regulatory", """
<h3>Entity</h3>
<ul>
<li><strong>Recommended vehicle:</strong> an Arkansas <strong>Telecommunications Cooperative</strong> under the Rural Telephone Cooperative Act (Act 51 of 1951). Articles are filed with the Secretary of State. A general cooperative is the alternative; that choice is an open decision for counsel.</li>
<li><strong>Tax:</strong> Subchapter T, so patronage dividends aren't taxed at the co-op level.</li>
<li><strong>Critical path:</strong> counsel and CPA engaged → name and registered agent → Articles filed → EIN → ARIN organization, AS number and IP space, bank and escrow → bylaws and organizational meeting (can now sign transit and take member capital) → FCC registration and data filings, with Corps, pole and road permits started in parallel.</li>
</ul>
<h3>Federal and state</h3>
<ul>
<li><strong>FCC:</strong> registration number and Broadband Data Collection filings; Form 499 and Universal Service contributions only if voice is offered; licensing for microwave paths; CBRS requires a spectrum-access account and certified installers.</li>
<li><strong>Arkansas:</strong> Secretary of State filings and DFA sales-tax registration for taxable equipment.</li>
</ul>
<h3>The lake: U.S. Army Corps of Engineers</h3>
<p>Beaver Lake is a federal reservoir managed under the Corps' Shoreline Management Plan. Any structure, cable landing or crossing on Corps shoreline or lakebed needs authorization: a shoreline use permit or real-estate outgrant, and Section 10/404 permits for work in or over the water. The design keeps sites on private host land above the Corps take line and crosses the lake by radio wherever possible. Radio signals over water need no permit; underwater cable is the heaviest case.</p>
<h3>Also</h3>
<ul>
<li>Pole attachments (Ozarks Electric, Carroll Electric, SWEPCO) and county road permits for fiber.</li>
<li>FAA review for 30–45 m towers.</li>
<li>Arkansas 811 before digging.</li>
<li>Zoning for head-ends.</li>
<li>Insurance.</li>
<li>Securities counsel for every member-capital instrument.</li>
</ul>
<blockquote><p>Not legal advice. Every item needs cooperative, securities and telecom counsel and a co-op-experienced CPA before filing.</p></blockquote>
""")

# ------------------------------------------------------------------------------ 15
sec("team", "Team", """
<p>Lean at the pilot stage: each role is a hat before it's a headcount, and DockOS lets a small team run a large network.</p>
""" + tbl(["Phase", "Roles"], [
    ["0 — Foundations", "Owner/CEO; network architect (RF and fiber); GIS analyst; software/DevOps engineer; regulatory and permitting lead; financing manager (part-time); bookkeeper/CPA (contract)"],
    ["1 — Pilot", "Field operations lead; 2–3 field technicians (fiber and wireless); 1–2 NOC and support technicians; procurement and inventory coordinator; sales and community manager"],
    ["2+ — Region and ring", "Field crews per zone, NOC shifts, support reps, construction manager, controller, HR"],
]) + """
<p>Ready-to-post job descriptions exist for every role. Technicians are cross-trained on boats and trucks, since the fleet is hybrid.</p>
""")

# ------------------------------------------------------------------------------ 16
sec("roadmap", "Roadmap", """
""" + tbl(["Phase", "When", "What happens"], [
    ["0 — Foundations", "Months 0–4", "Form the co-op; ARIN; two transit agreements; Corps and pole conversations; pilot design; host-site recruiting; member-capital campaign opens"],
    ["1 — Pilot", "Months 4–12", "Two head-ends, the first backbone segment, one lake crossing; 1–2 dock nodes; first paying members; real costs feed back into the model"],
    ["2 — Central region", "Years 1–2", "Complete the central Benton corridor; close cooperative/commercial debt on pilot proof; scale crews; formal NOC shifts"],
    ["3 — Ring closure", "Years 2–3", "Build the backbone around and across, including the ring-closing links; expand dock nodes and relays"],
    ["4 — Long tail", "Years 3–5", "Upper arms and sparse coves, each gated by pre-sales; fiber overbuild where wireless zones mature"],
]) + """
<p>Software leads the build slightly, so every zone is measured, sold and managed from data. The remaining module is the compliance advisor.</p>
""")

# ------------------------------------------------------------------------------ 17
sec("risks", "Risks and mitigations", tbl(["Risk", "Mitigation"], [
    ["Corps and permitting delays (the biggest schedule risk)", "Start at entity formation; dedicated permitting lead; radio crossings over underwater cable; sites above the Corps take line"],
    ["Single points of failure in the backbone", "Close the ring (section 5); dual-home the NW head-end; hot spares at the two remaining weak sites"],
    ["Tree canopy blocks more radio paths than expected", "LiDAR-informed design; 30–45 m towers; non-line-of-sight radios; relays and fiber"],
    ["Storm interruptions for wireless members", "Self-recovering equipment, surge standard, remote restart, honest disclosure, no bare 60 GHz on the backbone"],
    ["Thin take-up in sparse zones", "Per-zone build gate on reservations and capital"],
    ["Capital cost overruns", "Phase-gated spending; wireless-first mix; equipment financing"],
    ["Securities treatment of member capital or WAKE", "Two-rail design; counsel review before taking any money; no token sale ever"],
    ["Boat operations limited by weather and dock time", "Hybrid fleet; weather gate; turnaround measured and improved"],
    ["Incumbent price response", "Compete on reliability, symmetry and local service"],
    ["Key people and skills", "Documented standards, cross-training, DockOS doing the routine work"],
]))

# ------------------------------------------------------------------------------ 18
sec("reconcile", "Inconsistencies to reconcile", """
<p>Writing this paper surfaced places where earlier documents disagree with later findings. Each should be corrected before the plan is final:</p>
<ul>
<li><strong>Grants:</strong> the roadmap (doc 15) still mentions grants and federal RUS loans in Phases 2 and 4, and the team plan lists a grants manager, but the base case is grant-free (doc 13).</li>
<li><strong>Funding figures:</strong> doc 13 still cites $7.5M capital and a $3.1M peak, superseded by the LiDAR-informed $8.6M and $3.6M.</li>
<li><strong>Entity:</strong> the business plan (doc 06) suggests an LLC; the entity checklist (doc 19) recommends a telecommunications cooperative.</li>
<li><strong>"Redundant spine"</strong> wording in docs 01, 06 and the README predates the ring audit.</li>
<li><strong>IPv6 size:</strong> docs 01 and 17 say /32; the ARIN request and doc 21 use /36.</li>
<li><strong>Premises:</strong> the business plan's ~9,000 estimate is superseded by the verified 9,571.</li>
<li><strong>Short lake crossings</strong> are specified as "60 or 5 GHz" in the backbone design; see section 6.</li>
</ul>
""")

# ------------------------------------------------------------------------------ 19
sec("appendix", "Appendix: documents, pages and terms", """
<h3>Planning documents (repository)</h3>
""" + tbl(["Doc", "Subject"], [
    ["01–03", "Technology review, comparable networks, network architecture"], ["04–05", "Geography and zones; GIS plan"],
    ["06–08", "Business plan; operations; staffing (with job descriptions)"], ["09–11", "Accounting and pro forma; materials and BOM kits; procurement"],
    ["12–13", "Regulatory and permitting; grant-independent financing"], ["14–15", "DockOS architecture; roadmap"],
    ["16", "Cooperative governance and WAKE"], ["17", "Middle-mile and transit (with RFQ package)"],
    ["18", "Member-capital campaign"], ["19", "Entity formation checklist"], ["20", "Sites and real estate"],
    ["21", "Engineering design spec"], ["22", "Billing, provisioning, RADIUS"], ["23", "Dispatch, work orders, crew app"],
    ["24", "Network operations and outage management"],
]) + """
<h3>Companion pages</h3>
<ul>
<li><a href="https://claude.ai/artifact/L4Jq482X74PeXJkWBL71cS">Beaver Lake Network Map</a> — zones, nodes, backbone</li>
<li><a href="https://claude.ai/artifact/DSMpCES5QV2KJbGZhGjEV4">Pro Forma dashboard</a></li>
<li><a href="https://claude.ai/artifact/AiAAbkuYFqzFaeqwFQVMEc">Investor and lender deck</a></li>
<li><a href="https://claude.ai/artifact/Fk7Sbu2NjYmhffo5mwugHw">WAKE governance explainer</a></li>
<li><a href="https://claude.ai/artifact/LeEBTN21as8wm7EBQRtrpe">Join Boat Dock Network</a> — signup and pledges</li>
<li><a href="https://claude.ai/artifact/VdhypMHV8Z748GMJhgZiXK">Member voting</a></li>
<li><a href="https://claude.ai/artifact/5teoYVbPD7nKjV55wNN3KH">DockOS Crew</a></li>
<li><a href="https://claude.ai/artifact/XTgZQdX7AoB6URdGadwsNX">DockOS NOC</a></li>
</ul>
<p>Each page is private to its owner until shared.</p>
<h3>Terms</h3>
""" + tbl(["Term", "Meaning"], [
    ["WAKE", "The co-op's non-transferable governance unit, earned 1 per month of membership"],
    ["Patronage dividend", "Surplus returned to members in proportion to service purchased"],
    ["T0–T4", "Network tiers: head-end, core, dock node, relay, premises"],
    ["nLOS", "Non-line-of-sight radio that works through some foliage and obstruction"],
    ["CBRS", "3.55–3.7 GHz shared spectrum, used by registering each radio with a spectrum access system (FCC Part 96)"],
    ["SPOF", "Single point of failure: one link or site whose loss cuts members off"],
    ["Take rate", "Share of premises passed that become members"],
    ["Dock turnaround", "Minutes a boat stop costs beyond travel and the job itself"],
    ["RADIUS", "The system that authorizes each member's connection"],
]))

decisions = [
    ("D01", "Legal", "Which cooperative vehicle?", "Telecommunications cooperative (Act 51) · general cooperative", "Telecommunications cooperative, confirmed by counsel", "Section 14 · doc 19"),
    ("D02", "Sites", "Own or lease the two head-end sites, and where exactly?", "Buy fee simple · long ground lease · colocate", "Buy both; confirm the two known internet-buy locations can be owned", "Section 8 · doc 20"),
    ("D03", "Sites", "Should a lakeside head-end double as the boat and operations base?", "Combine · keep separate", "Combine if the parcel meets both sets of criteria", "Sections 8–9 · doc 20"),
    ("D04", "Reliability", "Close the ring: budget and method for the five added links", "Radio ($40k) · mixed · all fiber ($689k)", "Survey first; budget $40k plus contingency; fall back per link", "Section 5 · doc 24"),
    ("D05", "Reliability", "Give the northwest head-end a second connection?", "Yes · defer", "Yes", "Section 5 · doc 24"),
    ("D06", "Reliability", "The two remaining weak sites (N11, N05)", "New relay site · dual-radio hot spare · accept the risk", "Dual-radio hot spares now; relay sites if the zones grow", "Section 5"),
    ("D07", "Wireless", "The three short lake crossings", "5/6 GHz · 60 GHz with 5 GHz backup · licensed 18/23 GHz", "Licensed 23 GHz where capacity is needed, otherwise 5/6 GHz; no bare 60 GHz", "Section 6"),
    ("D08", "Wireless", "Access radio vendors and install standard", "Tarana + Cambium · Tarana + Ubiquiti · single vendor", "Tarana for tree-shadowed homes plus one line-of-sight vendor; watchdog and surge standard on every install", "Sections 3, 6 · docs 01, 10"),
    ("D09", "Members", "Adopt the wireless weather disclosure and require acknowledgment?", "Adopt as written · revise · don't require acknowledgment", "Adopt; wireless applicants acknowledge at signup", "Section 6"),
    ("D10", "Members", "Outage credit terms", "As proposed · different thresholds · claim-based", "As proposed; the board sets them in the member agreement", "Section 11 · doc 24"),
    ("D11", "Members", "Plan pricing", "As listed · adjust tiers", "As listed until real transit quotes arrive", "Section 11 · doc 06"),
    ("D12", "Operations", "Fleet mix", "Boat-heavy (original) · hybrid · truck-heavy", "Hybrid: trucks primary in truck-first zones, fewer and better-equipped boats", "Section 9 · doc 23"),
    ("D13", "Operations", "Pilot zones", "Prairie Creek, Beaver Shores, Monte Ne · other", "As ranked, subject to each zone's build gate", "Sections 1, 16"),
    ("D14", "Transit", "Transit paths A and B", "DSN/OzarksGo for A · RFQ scoring for B", "DSN/OzarksGo for A; B from the RFQ scorecard", "Section 7 · doc 17"),
    ("D15", "Funding", "Member-capital amounts and the zone build gate", "$200 / $100 / tiers; 25% and $75 per premises · adjust", "As modeled, confirmed by securities counsel", "Section 13 · doc 18"),
    ("D16", "Governance", "Give founding members a one-time WAKE grant?", "Yes (+12, within the cap) · no", "Yes, capped, so recognition doesn't become control", "Section 2 · doc 16"),
    ("D17", "Funding", "Stay grant-free, and remove grant references from the roadmap?", "Grant-free · grants as optional upside", "Grant-free base case; grants only as upside", "Sections 13, 18"),
    ("D18", "Finance", "Fold ring closure, fleet changes and backbone band choices into the model?", "Now · after surveys", "Carry a contingency now; replace it with survey results", "Section 12"),
    ("D19", "Legal", "Separate property company for owned land and towers?", "Single co-op · operating co-op plus property company", "Decide with counsel after formation", "Doc 06"),
    ("D20", "Operations", "Provider for member text and email notices", "Choose via doc 13 vendor review", "Pick one before the pilot; the sender is already built", "Section 11 · doc 24"),
]

now = dt.datetime(2026, 9, 23, 18, 0, tzinfo=dt.timezone.utc).isoformat()
state = {
    "meta": {"title": "Boat Dock Network", "kicker": "White paper · working draft",
             "subtitle": "A member-owned, grant-free fiber and wireless network for the whole shoreline of Beaver Lake, Arkansas",
             "version": 1, "status": "draft", "updated": now, "preparedFor": "Founders, members, lenders and counsel"},
    "sections": S,
    "decisions": [{"id": a, "area": b, "question": c, "options": d, "recommendation": e, "ref": f,
                   "status": "open", "decision": "", "note": ""} for a, b, c, d, e, f in decisions],
    "changelog": [{"v": 1, "date": now, "note": "First draft assembled from planning docs 01–24, the pro forma, the ring audit and the weather analysis."}],
}
for s in S:   # the executive summary counts the open decisions
    s["html"] = s["html"].replace("Twenty decisions", f"{len(decisions)} decisions".capitalize())
tpl = open(os.path.join(HERE, "template.html")).read()
js = json.dumps(state, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
out = os.path.join(HERE, "white_paper.html")
open(out, "w").write(tpl.replace("__STATE__", js))
print(out, f"{os.path.getsize(out) / 1024:.0f} KB", len(S), "sections", len(decisions), "decisions")

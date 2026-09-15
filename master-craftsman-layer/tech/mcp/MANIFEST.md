# Custom MCP servers — manifest

Ten trade-specific MCP servers this platform needs. `state-license-board/` is
built out as the reference implementation (SKILL.md + src/index.ts +
package.json, one placeholder tool). The rest share that exact shape and are
listed here rather than duplicated as boilerplate — generate each from the
reference when its data contract is identified.

| Server | Purpose | Data contract needed before build |
|--------|---------|-----------------------------------|
| `state-license-board` ✅ | Verify supervisor licenses (critical safety path) | Beachhead state board access method + ToU |
| `county-permits` | Pull/submit permit records per jurisdiction | County e-permitting portal / API |
| `utility-interconnect` | Interconnect + service-upgrade requests | Local utility interconnect process |
| `fsm-servicetitan` | Field service mgmt (jobs, dispatch, invoicing) | ServiceTitan API creds + tenant |
| `parts-ferguson` | Parts pricing/availability/ordering | Ferguson supplier account |
| `parts-grainger` | Parts pricing/availability/ordering | Grainger API / account |
| `parts-hdsupply` | Parts pricing/availability/ordering | HD Supply account |
| `ar-headset-fleet` | RealWear/Vuzix fleet mgmt + streams | Headset MDM / device API |
| `telematics-samsara` | Vehicle telematics, routing signals | Samsara API token |
| `insurance-bonding` | GL/bond quote + policy status | Carrier/broker integration |

## Fail-closed principle

Every stub returns `{status: "not-implemented", contract_needed: true}`.
Consumers must degrade safely: an unverified license blocks sign-off, a missing
permit blocks scheduling of permit-required work, and absent telematics falls
back to manual dispatch — never to an unsafe assumption of success.

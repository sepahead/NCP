# B01 current architecture review packet

> **CURRENT REVIEW SUBJECT — PROPOSED DECISIONS ONLY.** This packet binds the
> eleven proposed ADRs to clean pushed source commit
> `99672dd48bffe3f8504d4fb66d5a7c9140b122cf`. It contains zero review records.
> It does not accept an ADR, satisfy B01, authorize a rebaseline, certify
> interoperability or plant safety, or release NCP 1.0. B01 remains
> `IN_PROGRESS` until all exact external review and independent evidence
> requirements pass.

```json
{
  "schema": "ncp.b01-review-packet-lifecycle.v1",
  "state": "CURRENT"
}
```

```json
{
  "schema": "ncp.b01-review-subject.v1",
  "state": "CURRENT",
  "normative": false,
  "claim_boundary": "This generated registry records non-normative architecture decisions and structurally checked review claims. It cannot prove external authorship, role authority, or independence. It cannot satisfy B01 by itself, authorize the pre-release rebaseline or publication, or grant runtime identity, authority, plant action, safety, interoperability, or a scientific claim.",
  "promotion_blocked": true,
  "decision_set": {
    "schema": "ncp.b01-decision-set.v1",
    "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
    "domain_hex": "6e63702e6230312d6465636973696f6e2d7365742e763100",
    "sha256": "794c90203c662f1e12d78844c8ac8dcfc0162b0d3813b7df04cbe2e10cdd835a"
  },
  "review_policy": {
    "schema": "ncp.b01-review-policy.v1",
    "source_schema": "ncp.proposed-decision-registry-source.v1",
    "output_schema": "ncp.proposed-decision-registry.v1",
    "generator": {
      "path": "scripts/generate_decision_registry.py",
      "sha256": "4970e98e6f6a84c088a0965ff5b10b5a4b4b5e222a7a6c0f761f66d1ffd990d7",
      "bytes": 132781
    },
    "output_json_schema": {
      "path": "docs/adr/decision-registry.proposed.schema.v1.json",
      "sha256": "6977a739dc0328c993f002fc558934f76aa100555dd97448fe8f93e3d28c8e02",
      "bytes": 23695
    }
  },
  "source": {
    "commit": "99672dd48bffe3f8504d4fb66d5a7c9140b122cf",
    "tree": "b0c8858503753747ded585b91dd48095776dc241",
    "decision_source": {
      "path": "docs/adr/decision-registry.source.v1.json",
      "sha256": "fe4c81e1bdd32889f396f72bcc9ef094977d8f065a3ac814e90a43a013769a2b",
      "bytes": 14187
    }
  },
  "decisions": [
    {
      "id": "ADR-001",
      "title": "Separate simulation-service and plant-control sessions",
      "path": "docs/adr/0001-separate-simulation-and-plant-sessions.md",
      "module_paths": [],
      "content_sha256": "b76926aa12c0eb7e24a1de7cb7d130f798c07ae888cf38b2808aed43fc7adaf9",
      "bytes": 152215,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-001",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0001-separate-simulation-and-plant-sessions.md",
            "sha256": "b76926aa12c0eb7e24a1de7cb7d130f798c07ae888cf38b2808aed43fc7adaf9",
            "bytes": 152215
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "7ecbfe8dfceef42a14bccf74916025fc9ab519ede4bee4465edcf32bcd37529d"
      },
      "required_reviews": [
        {
          "role_id": "ncp-maintainer",
          "label": "NCP maintainer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "engram-owner",
          "label": "Engram owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-body-owner",
          "label": "Crebain body owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "independent-protocol-reviewer",
          "label": "independent protocol reviewer",
          "min_distinct_identities": 1,
          "requires_independence": true
        }
      ],
      "defect_ids": [
        "D01"
      ]
    },
    {
      "id": "ADR-002",
      "title": "Separate contract identity and release authorization",
      "path": "docs/adr/0002-contract-identity-and-release-authorization.md",
      "module_paths": [],
      "content_sha256": "d3f4d096933ae88389c068648f29eaf880d2e8b3318ba3aa5c52651fa73e7b44",
      "bytes": 16004,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-002",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0002-contract-identity-and-release-authorization.md",
            "sha256": "d3f4d096933ae88389c068648f29eaf880d2e8b3318ba3aa5c52651fa73e7b44",
            "bytes": 16004
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "7710e1610a5bf78a3dc269de4f1d93d6d9056d1bee7c311de1dd5bdfb756034c"
      },
      "required_reviews": [
        {
          "role_id": "protocol-reviewer",
          "label": "protocol reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "release-supply-chain-reviewer",
          "label": "release and supply-chain reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D04",
        "D13",
        "D17",
        "D19"
      ]
    },
    {
      "id": "ADR-003",
      "title": "Authenticate production ingress before interpretation",
      "path": "docs/adr/0003-authenticated-production-ingress.md",
      "module_paths": [],
      "content_sha256": "d3743d483114b24d5b08a3477b6525d927d5233be41c2609ee16209d7d4e8af4",
      "bytes": 21273,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-003",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0003-authenticated-production-ingress.md",
            "sha256": "d3743d483114b24d5b08a3477b6525d927d5233be41c2609ee16209d7d4e8af4",
            "bytes": 21273
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "2323d20a36394dc267a674ae5ea61935d480ecc5566d6850ac12dcbe29030fa4"
      },
      "required_reviews": [
        {
          "role_id": "security-cryptography-reviewer",
          "label": "security and cryptography reviewer",
          "min_distinct_identities": 2,
          "requires_independence": true
        },
        {
          "role_id": "transport-implementer",
          "label": "transport implementer",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D06",
        "D10"
      ]
    },
    {
      "id": "ADR-004",
      "title": "Attach observers with bounded grants and revocation",
      "path": "docs/adr/0004-observer-attach-grants-and-revocation.md",
      "module_paths": [
        "docs/adr/modules/adr-004-cross-store-observer-closure-and-enrollment.md"
      ],
      "content_sha256": "a192232e3cf97bafec8e55a02ee8f411a7c298256639bec5fdc7fbcd47506904",
      "bytes": 261552,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-004",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0004-observer-attach-grants-and-revocation.md",
            "sha256": "a192232e3cf97bafec8e55a02ee8f411a7c298256639bec5fdc7fbcd47506904",
            "bytes": 261552
          },
          {
            "kind": "module",
            "path": "docs/adr/modules/adr-004-cross-store-observer-closure-and-enrollment.md",
            "sha256": "ed70f11100eb0eee6377084206025309502e5c6275e9c49a1061c4e949e9f8fb",
            "bytes": 118633
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "ea0651c10b1c42d40f339532106cefcc5192afd8ad22981b15684dd5157f3e87"
      },
      "required_reviews": [
        {
          "role_id": "prisoma-owner",
          "label": "Prisoma owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "galadriel-owner",
          "label": "Galadriel owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "security-reviewer",
          "label": "security reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "ncp-source-provider-owner",
          "label": "NCP/source-provider owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "observer-anchor-infrastructure-owner-operator",
          "label": "observer-anchor infrastructure owner/operator",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "independent-anchor-security-distributed-systems-reviewer",
          "label": "independent anchor security/distributed-systems reviewer",
          "min_distinct_identities": 1,
          "requires_independence": true
        }
      ],
      "defect_ids": [
        "D02",
        "D05",
        "D20"
      ]
    },
    {
      "id": "ADR-005",
      "title": "Declare and retire every stream explicitly",
      "path": "docs/adr/0005-declared-stream-lifecycle.md",
      "module_paths": [],
      "content_sha256": "6c1e1baf207d3eb74cd3923f51c19eba673a54e199700be0fa62e9f39e4a3d29",
      "bytes": 38308,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-005",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0005-declared-stream-lifecycle.md",
            "sha256": "6c1e1baf207d3eb74cd3923f51c19eba673a54e199700be0fa62e9f39e4a3d29",
            "bytes": 38308
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "73384f873d12e9ff6eca4b41ce1fcb681d5908ad843d96c27f84ead8eb5f27f2"
      },
      "required_reviews": [
        {
          "role_id": "distributed-systems-reviewer",
          "label": "distributed-systems reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "engram-stream-owner",
          "label": "Engram stream owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "haldir-stream-owner",
          "label": "Haldir stream owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "galadriel-stream-owner",
          "label": "Galadriel stream owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-stream-owner",
          "label": "Crebain stream owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "prisoma-stream-owner",
          "label": "Prisoma stream owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D03"
      ]
    },
    {
      "id": "ADR-006",
      "title": "Use body-issued authority and receiver-local time",
      "path": "docs/adr/0006-body-issued-authority-and-time.md",
      "module_paths": [],
      "content_sha256": "b16c4cfbf4d93315e94991f1a7558861b308e56abf45683e3c82ab2a43d09f13",
      "bytes": 55367,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-006",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0006-body-issued-authority-and-time.md",
            "sha256": "b16c4cfbf4d93315e94991f1a7558861b308e56abf45683e3c82ab2a43d09f13",
            "bytes": 55367
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "a9a5cff24bfbdc8462acd15b025a52fd2ed31335a1ca59ea84c1ffa78753d13a"
      },
      "required_reviews": [
        {
          "role_id": "safety-reviewer",
          "label": "safety reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "distributed-systems-reviewer",
          "label": "distributed-systems reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "haldir-owner",
          "label": "Haldir owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-owner",
          "label": "Crebain owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D08",
        "D15"
      ]
    },
    {
      "id": "ADR-007",
      "title": "Journal body-issued command dispositions",
      "path": "docs/adr/0007-command-disposition-journal.md",
      "module_paths": [],
      "content_sha256": "833fd9b84650defd46b02731b5ebc871a06152d4ceb8d6ba559605a1d4c5fe83",
      "bytes": 221493,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-007",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0007-command-disposition-journal.md",
            "sha256": "833fd9b84650defd46b02731b5ebc871a06152d4ceb8d6ba559605a1d4c5fe83",
            "bytes": 221493
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "974564f616d53789846f93b5cd8f9abc4514189c7d1d52e66ea81a401953f293"
      },
      "required_reviews": [
        {
          "role_id": "plant-safety-reviewer",
          "label": "plant and safety reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "haldir-owner",
          "label": "Haldir owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-owner",
          "label": "Crebain owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D07"
      ]
    },
    {
      "id": "ADR-008",
      "title": "Separate stable routes from Galadriel extensions",
      "path": "docs/adr/0008-extension-namespace-and-galadriel-separation.md",
      "module_paths": [],
      "content_sha256": "3da4b8131bcb7ecc9b2c723b7a8a02d40242e37687fd7bbfca98d3034ec052f2",
      "bytes": 170617,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-008",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0008-extension-namespace-and-galadriel-separation.md",
            "sha256": "3da4b8131bcb7ecc9b2c723b7a8a02d40242e37687fd7bbfca98d3034ec052f2",
            "bytes": 170617
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "cb0853d68c64d89e87b22e6eec36db349b824ead1657141a0b99cd11fea68f77"
      },
      "required_reviews": [
        {
          "role_id": "protocol-reviewer",
          "label": "protocol reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "galadriel-owner",
          "label": "Galadriel owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "haldir-owner",
          "label": "Haldir owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-owner",
          "label": "Crebain owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D09"
      ]
    },
    {
      "id": "ADR-009",
      "title": "Bind semantic security state, rotation, and revocation",
      "path": "docs/adr/0009-security-state-rotation-and-revocation.md",
      "module_paths": [
        "docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md"
      ],
      "content_sha256": "b8031cdaa2ae7e3024ee4c623e99ff63bcb231353e66ee299888bec7b86841e4",
      "bytes": 257562,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-009",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0009-security-state-rotation-and-revocation.md",
            "sha256": "b8031cdaa2ae7e3024ee4c623e99ff63bcb231353e66ee299888bec7b86841e4",
            "bytes": 257562
          },
          {
            "kind": "module",
            "path": "docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md",
            "sha256": "47420d1b7a3b9bfa3ff767510c26e66520caa44ef735371d08faf4c16cc11800",
            "bytes": 74277
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "9dd098dea0786d83d09b0465db56da289f7a61b3b3705ef243ec49a1f3039b9c"
      },
      "required_reviews": [
        {
          "role_id": "security-reviewer",
          "label": "security reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "operations-reviewer",
          "label": "operations reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "supply-chain-reviewer",
          "label": "supply-chain reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "security-artifact-anchor-infrastructure-owner-operator",
          "label": "security-artifact-anchor infrastructure owner/operator",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "independent-anchor-security-reviewer",
          "label": "independent anchor security reviewer",
          "min_distinct_identities": 1,
          "requires_independence": true
        }
      ],
      "defect_ids": [
        "D16",
        "D20"
      ]
    },
    {
      "id": "ADR-010",
      "title": "Specify finite per-plane QoS and overload behavior",
      "path": "docs/adr/0010-plane-qos-retention-and-overload.md",
      "module_paths": [],
      "content_sha256": "4a326e610f1d9b942f7a0fa3a4e320b34f990062cf39067417f32015fcafc36c",
      "bytes": 15683,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-010",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0010-plane-qos-retention-and-overload.md",
            "sha256": "4a326e610f1d9b942f7a0fa3a4e320b34f990062cf39067417f32015fcafc36c",
            "bytes": 15683
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "26ef01e63136bea412d7f3d249f21978efaad48d1c9af2f20866d66725670999"
      },
      "required_reviews": [
        {
          "role_id": "real-time-performance-reviewer",
          "label": "real-time and performance reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "engram-consumer-reviewer",
          "label": "Engram consumer reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "haldir-consumer-reviewer",
          "label": "Haldir consumer reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "galadriel-consumer-reviewer",
          "label": "Galadriel consumer reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-consumer-reviewer",
          "label": "Crebain consumer reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "prisoma-consumer-reviewer",
          "label": "Prisoma consumer reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D14"
      ]
    },
    {
      "id": "ADR-011",
      "title": "Fix ecosystem dependency direction and plant handover",
      "path": "docs/adr/0011-ecosystem-topology-and-handover.md",
      "module_paths": [],
      "content_sha256": "7594ce4e746f4c2084e2ad7f40675684f0c9b68d33bffe2234a26688e49800ae",
      "bytes": 70553,
      "source_set": {
        "schema": "ncp.b01-adr-source-set.v1",
        "decision_id": "ADR-011",
        "sources": [
          {
            "kind": "main",
            "path": "docs/adr/0011-ecosystem-topology-and-handover.md",
            "sha256": "7594ce4e746f4c2084e2ad7f40675684f0c9b68d33bffe2234a26688e49800ae",
            "bytes": 70553
          }
        ],
        "digest_algorithm": "sha256(domain || u64be(projection_bytes) || projection)",
        "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
        "sha256": "3d0df976883070a88ada52c7d1bb554309959b2e6cb31ca68ee63de2cdeb452e"
      },
      "required_reviews": [
        {
          "role_id": "engram-owner",
          "label": "Engram owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "haldir-owner",
          "label": "Haldir owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "galadriel-owner",
          "label": "Galadriel owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-owner",
          "label": "Crebain owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "prisoma-owner",
          "label": "Prisoma owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "cortexel-owner",
          "label": "Cortexel owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "pid-rs-owner",
          "label": "pid-rs owner",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "independent-security-distributed-systems-reviewer",
          "label": "independent security and distributed-systems reviewer",
          "min_distinct_identities": 1,
          "requires_independence": true
        },
        {
          "role_id": "release-package-tooling-reviewer",
          "label": "release and package-tooling reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        },
        {
          "role_id": "crebain-plant-safety-reviewer",
          "label": "Crebain plant and safety reviewer",
          "min_distinct_identities": 1,
          "requires_independence": false
        }
      ],
      "defect_ids": [
        "D01",
        "D08",
        "D09",
        "D11",
        "D12",
        "D18"
      ]
    }
  ]
}
```

This machine-readable lifecycle block controls whether review capture is
permitted. Banner text is explanatory only. A `CURRENT` packet must contain
exactly one matching `CURRENT` review-subject block before it can receive review
records. A `SUPERSEDED` or `TEMPLATE` packet cannot contain that block or receive
review records.

## Current packet bindings

The generated review subject binds `decision_set.sha256`. The
decision-set digest covers all exact ADR bytes, role obligations, defect
mappings, review-policy version, and exact generator and output-schema
identities. It excludes review records, so later review capture does not change
the reviewed subject. A policy implementation or schema change makes an earlier
review stale.

The review workflow has these additional binding obligations:

- the clean pushed source commit and its resolved tree;
- the exact zero-review decision source SHA-256 and byte length at that commit;
- every ADR SHA-256 and byte length;
- the review-policy version and exact generator and output-schema SHA-256 and
  byte length;
- each stable `role_id`, label, minimum distinct identity count, and independence
  requirement;
- the current parser, model, resource, and complete-gate evidence;
- the exact owner-free v4 allocation identity, origin/signal, semantic-shape,
  semantic-subject, document-row, ADR-source-set, and provenance commitment
  suites and their artifact-declared known-answer vectors;
- the exact non-authorizing allocation proposal, its complete compiler source
  set, schema, compact input, ADR corpus, and proposal-row commitment;
- the local standard-library Node recomputation result, with its explicit
  non-external and non-independent claim boundary;
- the observer read/capture bridge v2 profile, its canonical-commitment suite
  and digest, its exact probe source and output bindings, and its
  actual-dispatch-byte substitution result;
- the external receipt format and retention path; and
- the separate B02 authorization and later N01 promotion boundaries.

The packet must not embed its own digest. The external review request and every
review record content-address the immutable packet bytes with
`review_packet_sha256`. This acyclic rule lets the generator compare that digest
with the current packet file.

The JSON block above has schema `ncp.b01-review-subject.v1` and state `CURRENT`.
It contains the exact decision-set and review-policy identities, source commit
and tree, claim boundary, promotion block, and all ADR digests, byte lengths,
role obligations, and defect mappings. It does not contain
`review_packet_sha256`.

The source currently has zero review records. The generator validates this
review-subject block immediately so reviewers do not receive an unchecked
subject. Once any record exists, it rejects a missing, duplicate, superseded,
template, or mismatched `CURRENT` block. It resolves every ADR in the block from
the named Git commit. It also requires that commit to contain the exact current
generator, output schema, and zero-review decision source. A record that claims
the current packet must match that block.

Composite local runs at the bound source commit covered every command in
`scripts/check.sh`. One uninterrupted attempt stopped only when crates.io timed
out during the Python source-distribution build. The exact failed step and
remaining suffix then passed separately. This is composite coverage, not one
uninterrupted complete-gate receipt.

The clean command `./prototypes/b01-architecture-evidence/run.sh` passed at that
commit. It covered 15,379 composition states and 169 observer-authorization
hostile inputs. It also covered 444 observer-capture hostile inputs, 547
freshness and acceptance cases, and 188 source-index hostile cases. Separate
Rust and TypeScript engines agreed on 22 content-bound ADR-example semantic
cases. They rejected all 90 registered bounded mutations. The verifier rejected
all registered hostile mutations.

The decision-probe verifier builds and canonicalizes a fresh replay oracle
before it serializes caller-controlled values. A hostile `dict`-subclass
self-test mutates shared state during caller serialization. It requires exactly
one oracle build before that serialization. It rejects candidate influence on
the oracle. These results are local preliminary evidence only. They do not
satisfy an external, independent, consumer, safety, performance, or release
gate.

Review capture follows an acyclic sequence:

1. commit and push the final ADR, role, generator, and schema source with zero
   review records;
2. run
   `python3 scripts/generate_decision_registry.py --emit-review-subject <commit>`
   for that exact 40-character commit, set the lifecycle to `CURRENT`, and insert
   the emitted block without modification;
3. commit and push the immutable packet without changing its reviewed inputs;
4. content-address those packet bytes in the external request and review
   records; and
5. add review records later without changing the packet or reviewed inputs.

Each reviewer must use a stable issuer-and-subject identity. A display name or
GitHub reaction is not sufficient. Each review must have an authenticated
external receipt and separate role-authorization evidence. A role that requires
independence must also have a separate retained content-addressed independence
assessment. A boolean claim alone does not qualify.

The source must retain each external receipt under
`evidence/implementation/reviews/B01/`. Each reference binds an absolute HTTPS
URL, SHA-256, byte length, media type, and regular non-symlink file. Role
authorization and the review receipt use separate files. A required independence
assessment uses a third file. The generator bounds both each file and the
aggregate retained evidence that one registry validation reads. Review,
role-authorization, independence, and condition-closure receipt paths, URLs, and
byte digests are exclusive across review records. One retained receipt cannot
impersonate multiple judgments.

An `ACCEPT_WITH_CONDITIONS` record does not count while a condition is open. A
resolution must bind exact evidence and a same-reviewer closure receipt for the
same ADR and decision-set digests. An ADR edit makes the old review stale and
requires a new review. Resolution evidence, the closure receipt, review receipt,
role authorization, and independence assessment use distinct retained evidence
paths. A superseding record must have a later timestamp than its predecessor.

The generator resolves the source commit as a real Git commit. It checks the
tree, zero-review decision source, generator, output schema, and every ADR blob
at that commit. It checks each digest and byte length. It also checks the review
against the current packet bytes. These structural checks do not prove external
authorship, role authority, or independence. Those facts remain B01 evidence
obligations.

A generated `ACCEPTED` registry does not advance B01 by itself. A B01
independent-pass receipt must bind the exact registry, packet, source
commit/tree, review policy, accepted ADR IDs, qualifying review IDs, and a
derived digest of each role's reviewer identity kind, implementation-owner
universe, role-authorization receipt, independence assessment, and external
review receipt. Two distinct non-owner external adjudicators must separately
bind and pass that complete subject and the same exact owner universe.
Each adjudication must bind a separate retained external receipt by public HTTPS
URL, repository-relative path, SHA-256, byte length, and media type. Those
receipts must use distinct URLs, paths, and byte digests. They cannot reuse any
review, role-authorization, independence, resolution, or condition-closure
evidence. Every content-addressed registry review-evidence file must remain a
regular current file and the exact same blob in the pushed B01 receipt commit.
The registry inputs, adjudication artifacts, and retained receipts must also be
exact regular blobs in that commit. The packet's zero-review source commit must
be a strict ancestor of the pushed B01 receipt commit, so that push carries the
exact review request in its history. Each adjudication must occur after every
qualifying review and condition closure, and before the B01 passing receipt.
B02 owner authorization binds the exact B01
ratification-receipt digest and uses another exclusive, content-addressed
retained receipt after the dependency-ready B02 start and before its passing
receipt.

This model closes D19 without promoting a file into `contract/`. B02 owns
rebaseline authorization. B03 owns exact registry allocations. N01 alone owns
mechanical normative promotion. N01 rejects a promoted copy that alters any
review, policy, evidence, decision-set, schema, generator, or predecessor
provenance field.

## Historical superseded packet

This packet requests human, same-digest review of the eleven **PROPOSED** NCP
1.0 architecture decisions. It is not an approval record. It does not accept an
ADR, change the normative contract, satisfy B01, authorize a rebaseline, certify
interoperability or plant safety, or release NCP 1.0.

### Exact review subject

- ADR/prototype source commit:
  `81941954f33078aa6a8dd85d70e392aae5469246`
- ADR/prototype source tree:
  `dc2c433e5e09cce9f03e981d9cbed44f84e72d00`
- clean full-gate checkpoint:
  `a9e0f48520649becc5507fc7d0ba069e4e20af92`
- clean full-gate tree:
  `803380bc420b4e4723e3663ecceaf5652977fb3d`
- candidate: unreleased, release-blocked `1.0.0-rc.1`
- wire: `1.0`
- compact proto hash: `163acc57d8a62b66`
- complete normative digest:
  `9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90`
- exact `contract/manifest.v1.json` file SHA-256:
  `7a71920ebbd4df59e00a0f83026280de1e9395a545ecab1f879d13b1a1ba1e97`
- proposed registry file SHA-256:
  `e44cf8ba4e47558fcd768ce39dd48d64dd9262d96ff1502ed4f25bfc9d6850ba`

The later packet/evidence commit adds this review surface, the retained full-check
log, and generated coordination/audit mirrors; it does not alter the ADR bytes
below. A review is valid only for the exact ADR SHA-256 values it names. Any later
ADR edit invalidates that review.

### Decisions and required roles

| ADR | Exact content SHA-256 | Required reviewer roles |
|---|---|---|
| [ADR-001](0001-separate-simulation-and-plant-sessions.md) | `c379fd8d4d69c47dd7744a36da142164a0012279b2b3dafa0c230bba860c904b` | NCP maintainer; Engram owner; Crebain body owner; independent protocol reviewer |
| [ADR-002](0002-contract-identity-and-release-authorization.md) | `cd00a501f10d444eb23c7d8076de4f08862c3225c662ae9b0571fa8e4cd0f103` | protocol reviewer; release and supply-chain reviewer |
| [ADR-003](0003-authenticated-production-ingress.md) | `8aac232e1c60a74eb0875885fd84641f1186e4bfbf72b192787e02c83aa44545` | two independent security/cryptography reviewers; transport implementer |
| [ADR-004](0004-observer-attach-grants-and-revocation.md) | `cba3960513a4d40d1f4692580c3b4927bea57979f4703aab3c188f260b4a9656` | Prisoma owner; Galadriel owner; security reviewer |
| [ADR-005](0005-declared-stream-lifecycle.md) | `6760b9e545ccee75a2f8864d652603cd4b2e0d1e261fa89e56c319b7de56820e` | distributed-systems reviewer; Engram, Haldir, Galadriel, Crebain, and Prisoma stream owners |
| [ADR-006](0006-body-issued-authority-and-time.md) | `486501f2711aabf9addcc8b9fd4db2baaa49e125593591fbf8674f7220076053` | safety reviewer; distributed-systems reviewer; Haldir owner; Crebain owner |
| [ADR-007](0007-command-disposition-journal.md) | `c5411a4379ea8ae65887a7006ec233bae01f2279d026421c6ac366dde9406373` | plant/safety reviewer; Haldir owner; Crebain owner |
| [ADR-008](0008-extension-namespace-and-galadriel-separation.md) | `1379477feebd886823d1511af5df0b7a7019795aef9ee8023147a4ef0a5f56b6` | protocol reviewer; Galadriel owner; Haldir owner; Crebain owner |
| [ADR-009](0009-security-state-rotation-and-revocation.md) | `9adea1e3ad1a3a902860440ad2d3d88863e7eec7e1bd64ac50a048898a6c336a` | security reviewer; operations reviewer; supply-chain reviewer |
| [ADR-010](0010-plane-qos-retention-and-overload.md) | `9f67034f1b45a74ccbdd7726a387e58a411db5e5817f3a2042a20a1db94f213e` | real-time/performance reviewer; Engram, Haldir, Galadriel, Crebain, and Prisoma consumer reviewers |
| [ADR-011](0011-ecosystem-topology-and-handover.md) | `96d243fd41868a70fc00c0f309a5f87e0058f6fce5308e2c98d147e18f76421f` | every named consumer owner; pid-rs owner; independent security/distributed-systems reviewer; Crebain plant/safety reviewer |

The generated [proposed registry](decision-registry.proposed.v1.json) is the
machine-readable digest and role inventory. It remains non-normative, contains
zero review records, and is deliberately outside `contract/`.

### Ecosystem decision under review

The dependency and authority direction is standalone-first:

- NCP is a neutral provider and depends on no consumer application.
- Engram simulation responder and plant commander are separate optional roles.
- Direct Engram command and Haldir-gated command are mutually exclusive for one
  live body authority term.
- In gated mode, Engram sends a Haldir-local signed intent. Haldir creates a new
  NCP command under Haldir's principal and current Crebain-issued lease; Engram
  bytes never transfer identity or authority.
- Crebain remains the sole NCP body, lease issuer, final software actuator
  admission authority, and body command-disposition owner.
- Galadriel's NCP observer is read-only. Its separate default-off assessor is
  push-only and limited to `RECORD_ONLY` or authenticated `DENY_TIGHTEN`.
- Haldir owns local policy and applied-deny state. Its assessment disposition is
  an authenticated policy receipt, not a body command disposition or authority.
  Missing disposition never lets Galadriel infer `APPLIED_DENY`.
- Prisoma is read-only/offline; pid-rs is a protocol-neutral leaf; Cortexel is a
  labeled export sink. None is an NCP plant peer or command-path dependency.

Native v0.8-to-1.0 migration is a complete quiesced body-profile cut. Old
admission/listeners/principals/publishers and bounded queues close before a fresh
native session opens. Rollback is another complete cut with a fresh compatible
v0.8 incarnation. Neither direction permits dual-stack body admission or revival
of pre-cutover traffic. Generation and stream-epoch UUIDs are equality fences,
not counters.

### Current consumer baseline observation

These observations prevent copied files, active worktrees, or prerelease branches
from being mistaken for installed native-1.0 evidence. They are not review or
qualification receipts.

- Galadriel `12b8b05878fffcdf797405a4b31822e07948d3c0` is a local 0.9 source-candidate
  line whose candidate ref is pushed; its NCP compatibility remains historical
  v0.8, not native 1.0.
- Haldir `bb6c0a7b27bbc57fe9935f80e22d06ca3b60e8ba` documents the v0.8 Gate boundary
  correctly but is not a native-1.0 consumer receipt.
- Engram `dce24097b63161f4d24ad8ec1a20e0673bdc2c4c` has a native-1.0 migration in
  progress, but active unrelated work and copied protocol material establish no
  installed interoperability.
- Crebain `0a58a5b8dd799884ddb06f1308b1748216fab322`, Prisoma
  `63cff105e0e40281376e6f827d7782e9b351961a`, Cortexel
  `f49ff3554da95e26d9ba684c1e97c324e2597f16`, and pid-rs
  `adbd9026da1490a3c39663970ba4c2fc70a42376` retain the authority boundaries
  above. Active Cortexel/pid-rs work is unrelated and was not modified here.

### Preliminary challenge evidence

The retained result is
[`preliminary-architecture-8194195.v1.json`](../../evidence/implementation/working/B01/preliminary-architecture-8194195.v1.json),
SHA-256
`3f140dad12147500048644899f69893c1dd985d0001c900ec66b18143be51fe7`.
Its exact clean-source log is retained as
[`preliminary-architecture-8194195.log.gz`](../../evidence/implementation/working/B01/preliminary-architecture-8194195.log.gz),
SHA-256
`eb885f3c430e41f3386a860fc9cd74e23b4a1244ed94d03db281d7565d371603`.

Within their declared finite abstractions, the models explored 11,444 commander
composition states, 35 deny-lifecycle states, and 1,415 complete wire-cutover
states. All 23 registered Python mutations and four SMT mutations were detected;
all eleven registered SMT checks passed. Queue isolation, bounded parser/journal,
and local real-Ed25519 screens passed their explicit prototype bounds.

The complete local repository gate passed at `a9e0f48`. The raw log SHA-256 is
`8dcba99800e4af9ea7f672a51cadc8e91edbee1d5b9ff94cb5a2b18f38620daf`;
the retained deterministic
[`full-check-a9e0f48.log.gz`](../../evidence/implementation/working/B01/full-check-a9e0f48.log.gz)
SHA-256 is
`11042f9980566d0dbc5687957c2045f6dc902e7a2d212d9769dbc9d834e4b67a`.

Five usable exact `claude-fable-5` consultations are recorded in the
[consultation log](../research/b01-fable-architecture-consultations.md). The
latest response SHA-256 is
`080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`.
External-model advice is challenge input only and satisfies no review role.

### Reproduction commands

From an exact checkout of `a9e0f48520649becc5507fc7d0ba069e4e20af92`:

```bash
python3 scripts/check_implementation_ledger.py --self-test
python3 scripts/generate_implementation_ledger.py --check
python3 scripts/generate_decision_registry.py --self-test --check
python3 scripts/check_adr_examples.py --self-test
python3 scripts/generate_audit_artifacts.py --self-test --check
python3 scripts/check_audit_artifacts.py --self-test
prototypes/b01-architecture-evidence/run.sh
scripts/check.sh
```

Reviewers should independently compute the ADR SHA-256 values rather than trust
this packet. Local reproduction is useful challenge evidence but cannot replace
the required independent role and content-bound judgment.

### Required review focus

Review the selected ADRs through all three perspectives and the ten lenses named
in each ADR. In particular, try to find a counterexample involving:

- payload identity being mistaken for transport authentication;
- overlapping direct/gated leases or admission during handover;
- stale generation, term, lease, stream epoch, sequence, or delayed command;
- simulation state satisfying plant authority;
- assessment expiry, restart, retraction, disable, replay, forged disposition,
  queue overflow, or missing evidence widening permission;
- v0.8/native-1.0 dual admission or rollback revival of old traffic;
- observer/extension overload delaying control, disposition, watchdog, or
  fail-safe work;
- Prisoma, pid-rs, or Cortexel acquiring a hidden command-path edge;
- an unknown/default value granting capability, identity, success, or safety;
  and
- migration, packaging, or local tests being overstated as release or installed
  interoperability evidence.

### Replacement review response fields

```text
review_id:
adr_id:
role_id:
reviewer stable issuer-and-subject identity:
identity kind: PERSON | TEAM
implementation-owner identities:
independence_claimed: true | false
decision_set_sha256:
adr_content_sha256:
adr_bytes:
source_commit:
source_tree:
review_packet_sha256:
decision: ACCEPT | REJECT | ACCEPT_WITH_CONDITIONS
conditions and exact resolution requirements:
role-authorization receipt URL, path, SHA-256, bytes, media type:
independence-assessment receipt URL, path, SHA-256, bytes, media type, or null:
external-review receipt URL, path, SHA-256, bytes, media type:
timestamp_utc:
supersedes review_id or null:
```

An `ACCEPT_WITH_CONDITIONS` is not an acceptance until every condition is closed
against the same exact bytes and decision-set digest. The same reviewer must
authenticate the closure. Model output, an AI review, an implementation-owner
self-review, a local green test, or a GitHub reaction does not satisfy an
independent reviewer role.

### Explicit non-claims and remaining gates

All ADRs remain `PROPOSED`; B01 remains `IN_PROGRESS`; the generated registry has
zero review records. The normative contract is unchanged. Canonical TLA+,
refinement, Kani, installed independent peers, live mTLS/ACL/rotation/revocation,
fault/soak, duration fuzz/sanitizers, performance qualification, signatures,
SBOM/provenance, clean-room reproduction, plant validation, all exact consumer
role qualifications, publication, and post-publication validation remain
separate `NOT RUN` or blocked gates. NCP ESTOP is not physical certification and
no universal zero-safe action is claimed.

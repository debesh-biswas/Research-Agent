/* Sample weeks for the reading desk. Counts and cards are layout data, not a live run. */
window.DESK = {
  topics: [
    {
      id: "embodied_spatial_intelligence",
      name: "Embodied Spatial Intelligence",
      runs: [
        {
          id: "esi-2026-09-28",
          periodStart: "2026-09-18",
          periodEnd: "2026-09-28",
          status: "completed",
          durationSeconds: 840,
          models: ["qwen3:8b", "z-ai/glm-5.3-flash"],
          historyPeriods: 1,
          summary: {
            candidatesDiscovered: 126,
            candidatesDeduplicated: 98,
            papersClassified: 64,
            papersSelected: 5,
            downloadsSucceeded: 5,
            parseFailures: 0,
            deepReads: 3,
            errors: 0,
          },
          errors: [],
          executiveSummary:
            "The papers that mattered this week stop treating a home as a grid to localize in. Three of them give the agent a memory it can name: rooms, doors, and the objects that usually sit there. RoomGraph is the first benchmark in this topic that checks whether that memory is still right on a second visit. The remaining disagreement is practical. In cluttered rooms, a language map did not beat a carefully maintained occupancy grid.",
          developments: [
            {
              text: "Named spatial memory showed up in three methods. All of them update a topological map from language and keep the metric layer for motion.",
              paperIds: ["esi-topo", "esi-roomgraph", "esi-affordance"],
            },
            {
              text: "RoomGraph scores whether a memory survives a second visit. Earlier navigation sets in this topic did not.",
              paperIds: ["esi-roomgraph"],
            },
            {
              text: "Occupancy grids still win once furniture moves. The language-map papers do not cite that failure study.",
              paperIds: ["esi-grids"],
            },
          ],
          directions: [
            {
              text: "Persistence across a second visit is replacing single-run navigation success as the claim worth making.",
              paperIds: ["esi-roomgraph", "esi-topo"],
            },
          ],
          methods: [
            {
              text: "A pose graph underneath, with short language notes on stable regions, is the pattern in the deep reads.",
              paperIds: ["esi-topo", "esi-affordance"],
            },
          ],
          datasets: ["HomeWalk-12", "HM3D"],
          benchmarks: ["RoomGraph persistence split"],
          contradictions: [
            {
              text: "Language-conditioned topological maps report fewer navigation failures than occupancy grids. The clutter study finds the opposite when furniture moves between visits.",
              paperIds: ["esi-topo", "esi-grids"],
            },
          ],
          changes: [
            "The previous period only summarized metric SLAM. This is the first week a persistence benchmark cleared the deep-read bar.",
          ],
          gaps: [
            {
              title: "Unobserved layout change",
              description:
                "No paper tests whether a named memory survives a layout change the agent did not watch.",
              paperIds: ["esi-topo", "esi-grids", "esi-roomgraph"],
            },
          ],
          ideas: [
            {
              title: "Move three objects, then revisit",
              hypothesis:
                "A language map will keep more second-visit success than an occupancy grid if the notes are refreshed, and lose that lead if they are not.",
              motivation:
                "The two deep reads disagree, and neither runs the other's protocol.",
              direction:
                "Replay the RoomGraph second-visit split after silently moving three objects.",
              paperIds: ["esi-roomgraph", "esi-grids"],
            },
          ],
          readingOrder: {
            essential: ["esi-topo", "esi-roomgraph"],
            useful: ["esi-grids"],
            peripheral: ["esi-affordance", "esi-survey"],
          },
          papers: [
            {
              id: "esi-topo",
              title: "Language-Conditioned Topological Maps for Indoor Navigation",
              authors: ["Mei Chen", "Luis Ortiz", "Adewale Adeyemi"],
              date: "2026-09-22",
              venue: "ICRA",
              doi: "10.1109/icra.2026.0418",
              arxivId: "2609.11204",
              action: "deep_read",
              type: "method",
              relevance: "high",
              abstractOnly: false,
              citationCount: 3,
              problem:
                "Home robots still get lost after a chair moves, because the map they trust is a grid of occupied cells rather than a set of places they can talk about.",
              contribution:
                "A topological map whose nodes are rooms and doorways, updated from the robot's own language notes, with the metric layer left in place for motion.",
              method:
                "The robot builds a pose graph as usual, then names each stable region with a short description. On the next visit it matches those descriptions before it trusts the old geometry.",
              datasets: ["HomeWalk-12", "HM3D"],
              benchmarks: ["RoomGraph persistence split"],
              results: [
                "Second-visit navigation success rose from 61% to 78% when the furniture stayed put.",
                "The gain disappeared when three large objects moved and the notes were not refreshed.",
              ],
              strengths: [
                "The metric map stays, so the planner does not have to change.",
                "The failure case is reported beside the gain.",
              ],
              limitations: [
                "The language notes are written by the same model that is being evaluated, so the names are not an independent label.",
                "The twelve apartments share a similar floor plan.",
              ],
              claims: [
                {
                  text: "Second-visit success was 78% when the layout was unchanged.",
                  section: "Experiments",
                  page: 6,
                },
              ],
              relevance:
                "A named map that survives a second visit is the spatial memory this topic is tracking, and the clutter failure is the open problem.",
            },
            {
              id: "esi-roomgraph",
              title: "RoomGraph: A Benchmark for Persistent Spatial Memory",
              authors: ["Priya Nair", "Jonah Ellison"],
              date: "2026-09-20",
              venue: "CoRL",
              doi: "10.48550/arxiv.2609.09811",
              arxivId: "2609.09811",
              action: "deep_read",
              type: "benchmark",
              relevance: "high",
              abstractOnly: false,
              citationCount: 1,
              problem:
                "Navigation benchmarks score a single visit. They cannot tell a robot that remembers a home from one that is lucky on the day.",
              contribution:
                "A second-visit split: the robot leaves, time passes, and the score is whether its memory of rooms and doorways is still right.",
              method:
                "Forty scanned apartments are visited twice. Between visits, zero, one, or three pieces of furniture move. Memory is scored separately from path success.",
              datasets: ["RoomGraph"],
              benchmarks: ["RoomGraph persistence split"],
              results: [
                "Single-visit success and second-visit memory disagree on 11 of 40 homes.",
                "Methods that only publish single-visit numbers look tied until the second visit.",
              ],
              strengths: [
                "The split is public and the moved objects are listed.",
                "Memory is scored on its own, not hidden inside path success.",
              ],
              limitations: [
                "Objects move between visits, never during a visit.",
                "Language descriptions in the set were written by the authors, not by a robot.",
              ],
              claims: [
                {
                  text: "Single-visit success and second-visit memory disagree on 11 of 40 homes.",
                  section: "Results",
                  page: 5,
                },
              ],
              relevance:
                "This is the first benchmark in the topic that makes persistence a number other papers can be compared on.",
            },
            {
              id: "esi-grids",
              title: "When Metric Maps Lie: Occupancy Grids in Cluttered Homes",
              authors: ["Elena Voss", "Marc Duval"],
              date: "2026-09-19",
              venue: "IROS",
              doi: "10.1109/iros.2026.2201",
              arxivId: "2609.08440",
              action: "deep_read",
              type: "application",
              relevance: "high",
              abstractOnly: false,
              citationCount: 6,
              problem:
                "A clean occupancy grid looks reliable in a lab and then sends a home robot through a chair that was not there yesterday.",
              contribution:
                "A failure study: once three or more large objects move, a maintained occupancy grid navigates more safely than the published language maps.",
              method:
                "The same trajectories are replayed on a grid that is updated from depth, and on two language maps that keep their first-visit notes.",
              datasets: ["HomeWalk-12"],
              benchmarks: ["RoomGraph persistence split"],
              results: [
                "With three moved objects, the grid had fewer collisions than either language map.",
                "The language maps won only on the trials where nothing moved.",
              ],
              strengths: [
                "It uses the other papers' homes instead of a private test set.",
                "Collisions are counted separately from arrival.",
              ],
              limitations: [
                "The language maps were not allowed to refresh their notes, which is the setting where they already say they fail.",
                "Only depth updates the grid. Vision-only robots are out of scope.",
              ],
              claims: [
                {
                  text: "With three moved objects, the occupancy grid had fewer collisions than either language map.",
                  section: "Comparison",
                  page: 7,
                },
              ],
              relevance:
                "It is the counter-result to this week's main claim, and the report should not bury it.",
            },
            {
              id: "esi-affordance",
              title: "Affordance Fields from Egocentric Video",
              authors: ["Hana Ito", "Chris Bell"],
              date: "2026-09-21",
              venue: "CVPR Workshops",
              doi: null,
              arxivId: "2609.10112",
              action: "summarize",
              type: "method",
              relevance: "medium",
              abstractOnly: false,
              citationCount: 0,
              problem:
                "A map of free space does not say which surface can be sat on, opened, or avoided.",
              contribution:
                "A field, painted from egocentric video, that marks sittable, openable, and graspable surfaces on top of a room map.",
              method:
                "Short video clips vote for an affordance at each surface. The votes are attached to the topological node for that room.",
              datasets: ["Ego4D room subset"],
              benchmarks: [],
              results: [
                "Openable surfaces were marked more reliably than graspable ones.",
              ],
              strengths: ["The field attaches to a map the other papers already build."],
              limitations: [
                "No navigation result. The paper stops at the painted map.",
                "The room subset is small and chosen by hand.",
              ],
              claims: [
                {
                  text: "Openable surfaces were marked more reliably than graspable ones.",
                  section: "Evaluation",
                  page: 4,
                },
              ],
              relevance:
                "Useful context for what a named room could store, and not yet a navigation result.",
            },
            {
              id: "esi-survey",
              title: "Spatial Memory in Embodied Agents, 2024–2026",
              authors: ["Noah Park"],
              date: "2026-09-18",
              venue: "arXiv",
              doi: null,
              arxivId: "2609.07710",
              action: "summarize",
              type: "survey",
              relevance: "medium",
              abstractOnly: false,
              citationCount: 2,
              problem:
                "The phrase spatial memory covers grids, scene graphs, and language notes, and the papers rarely say which one they mean.",
              contribution:
                "A sort of the last two years into metric maps, topological maps, and language notes, with a table of what each one is scored on.",
              method: "Literature survey. No new experiment.",
              datasets: [],
              benchmarks: [],
              results: [
                "Most reported numbers are still single-visit path success.",
              ],
              strengths: ["The table makes the missing second-visit numbers obvious."],
              limitations: [
                "It closes before RoomGraph, so this week's benchmark is not in the table.",
              ],
              claims: [
                {
                  text: "Most reported numbers are still single-visit path success.",
                  section: "Discussion",
                  page: 9,
                },
              ],
              relevance:
                "Background for the change this week. The survey itself is not a new result.",
            },
          ],
        },
        {
          id: "esi-2026-09-14",
          periodStart: "2026-09-04",
          periodEnd: "2026-09-14",
          status: "degraded",
          durationSeconds: 620,
          models: ["qwen3:8b"],
          historyPeriods: 0,
          summary: {
            candidatesDiscovered: 98,
            candidatesDeduplicated: 77,
            papersClassified: 40,
            papersSelected: 2,
            downloadsSucceeded: 1,
            parseFailures: 1,
            deepReads: 1,
            errors: 2,
          },
          errors: [
            {
              category: "PDF_PARSE_ERROR",
              message: "One PDF parsed as empty text. That card uses the abstract.",
              paperId: "esi-slam",
            },
            {
              category: "RATE_LIMIT",
              message: "Semantic Scholar answered 429. Discovery continued with the other sources.",
              paperId: null,
            },
          ],
          executiveSummary:
            "This period only reached metric SLAM. One paper was readable in full. The other card is an abstract skim because the PDF could not be parsed. Nothing here yet tests whether a robot remembers a home on a second visit.",
          developments: [
            {
              text: "Doorway graphs from laser scans were the only deep read, and they score a single visit.",
              paperIds: ["esi-doors"],
            },
          ],
          directions: [],
          methods: [
            {
              text: "Laser doorway graphs remain the default map in this period.",
              paperIds: ["esi-doors"],
            },
          ],
          datasets: ["HomeWalk-12"],
          benchmarks: [],
          contradictions: [],
          changes: ["No earlier week was on file. This run is the baseline."],
          gaps: [
            {
              title: "No second visit",
              description: "Every selected paper scores the robot on the day it built the map.",
              paperIds: ["esi-doors", "esi-slam"],
            },
          ],
          ideas: [],
          readingOrder: {
            essential: ["esi-doors"],
            useful: ["esi-slam"],
            peripheral: [],
          },
          papers: [
            {
              id: "esi-doors",
              title: "Doorway Graphs from Laser Scans",
              authors: ["Elena Voss"],
              date: "2026-09-09",
              venue: "ICRA",
              doi: "10.1109/icra.2026.0188",
              arxivId: null,
              action: "deep_read",
              type: "method",
              relevance: "medium",
              abstractOnly: false,
              citationCount: 4,
              problem: "Room segmentation from a laser scan still breaks across open doorways.",
              contribution:
                "A doorway graph that splits a scan into rooms without a learned model.",
              method: "Gap detection in the scan, then a graph cut at each doorway.",
              datasets: ["HomeWalk-12"],
              benchmarks: [],
              results: ["Room labels matched the floor plan on 31 of 40 homes."],
              strengths: ["No training set. The rule is inspectable."],
              limitations: ["Single visit only. A moved door is out of scope."],
              claims: [
                {
                  text: "Room labels matched the floor plan on 31 of 40 homes.",
                  section: "Results",
                  page: 4,
                },
              ],
              relevance: "A metric baseline the later language maps should be compared with.",
            },
            {
              id: "esi-slam",
              title: "Metric SLAM Notes for Home Robots",
              authors: ["Jonah Ellison"],
              date: "2026-09-06",
              venue: "arXiv",
              doi: null,
              arxivId: "2609.04102",
              action: "summarize",
              type: "survey",
              relevance: "low",
              abstractOnly: true,
              citationCount: 0,
              problem: "Home-robot papers inherit SLAM systems that were tuned for offices.",
              contribution:
                "Notes on which metric SLAM systems show up in home-robot papers, from the abstract only.",
              method: "Not available. The PDF parsed as empty text.",
              datasets: [],
              benchmarks: [],
              results: ["The abstract lists four SLAM systems and no second-visit number."],
              strengths: [],
              limitations: ["Abstract only. Treat every detail below the citation as unverified."],
              claims: [],
              relevance: "Kept so the miss is visible. It is not evidence for a finding.",
            },
          ],
        },
      ],
    },
    {
      id: "computer_vision",
      name: "Computer Vision",
      runs: [
        {
          id: "cv-2026-09-28",
          periodStart: "2026-09-18",
          periodEnd: "2026-09-28",
          status: "degraded",
          durationSeconds: 994,
          models: ["qwen3:8b", "z-ai/glm-5.3-flash"],
          historyPeriods: 0,
          summary: {
            candidatesDiscovered: 471,
            candidatesDeduplicated: 390,
            papersClassified: 250,
            papersSelected: 4,
            downloadsSucceeded: 3,
            parseFailures: 1,
            deepReads: 3,
            errors: 3,
          },
          errors: [
            {
              category: "RATE_LIMIT",
              message: "Semantic Scholar answered 429. That source was skipped for this run.",
              paperId: null,
            },
            {
              category: "PDF_DOWNLOAD_ERROR",
              message: "No legal PDF for one selected paper. The card keeps the abstract.",
              paperId: "cv-drift",
            },
            {
              category: "MODEL_API_ERROR",
              message: "The strong model failed one card. The local model finished it.",
              paperId: "cv-tokens",
            },
          ],
          executiveSummary:
            "Detection at high resolution is the development that held up. Token merging cut the cost of large images without moving the accuracy number on the benchmark that matters. A second paper argues local features are doing more of that work than the transformer story admits. One selected paper is an abstract only, so it is not used as evidence.",
          developments: [
            {
              text: "Adaptive token merging kept detection accuracy on large images while reading fewer tokens.",
              paperIds: ["cv-tokens"],
            },
            {
              text: "A re-evaluation says recent vision transformers still depend on local features the papers treat as a detail.",
              paperIds: ["cv-local"],
            },
          ],
          directions: [
            {
              text: "Honest splits are becoming a paper of their own, not a footnote in a method paper.",
              paperIds: ["cv-occ"],
            },
          ],
          methods: [
            {
              text: "Merging similar tokens before the expensive layers is the concrete method in the essential read.",
              paperIds: ["cv-tokens"],
            },
          ],
          datasets: ["OpenOcc"],
          benchmarks: ["COCO", "OpenOcc honest split"],
          contradictions: [
            {
              text: "Token merging presents itself as architecture-neutral. The local-feature paper says the accuracy holds only when those features stay in the stem.",
              paperIds: ["cv-tokens", "cv-local"],
            },
          ],
          changes: ["No earlier computer-vision week is stored. This run stands alone."],
          gaps: [
            {
              title: "Fleet cameras",
              description:
                "Nothing selected measures whether a detector stays calibrated after months on the same cameras.",
              paperIds: ["cv-drift"],
            },
          ],
          ideas: [
            {
              title: "Re-run token merging without the local stem",
              hypothesis:
                "The reported savings shrink once the local features the second paper isolates are removed.",
              motivation: "The two deep reads describe the same accuracy with different causes.",
              direction: "Ablate the stem on the same COCO split both papers use.",
              paperIds: ["cv-tokens", "cv-local"],
            },
          ],
          readingOrder: {
            essential: ["cv-tokens"],
            useful: ["cv-local", "cv-occ"],
            peripheral: ["cv-drift"],
          },
          papers: [
            {
              id: "cv-tokens",
              title: "Adaptive Token Merging for High-Resolution Detection",
              authors: ["Lina Ortiz", "Samir Shah"],
              date: "2026-09-24",
              venue: "CVPR",
              doi: "10.48550/arxiv.2609.15002",
              arxivId: "2609.15002",
              action: "deep_read",
              type: "method",
              relevance: "high",
              abstractOnly: false,
              citationCount: 2,
              problem:
                "High-resolution detection still spends most of its compute on tokens that look like their neighbors.",
              contribution:
                "A merge step that collapses similar tokens before the expensive layers and restores them before the detection head.",
              method:
                "Similarity is measured inside each window. Tokens above a threshold share a representation until the head.",
              datasets: ["COCO"],
              benchmarks: ["COCO"],
              results: [
                "Large-image detection used 38% fewer tokens at the same box accuracy.",
              ],
              strengths: ["The threshold is reported, and the head is unchanged."],
              limitations: [
                "The local stem is left untouched, which is exactly the piece the companion paper says is doing the work.",
              ],
              claims: [
                {
                  text: "Large-image detection used 38% fewer tokens at the same box accuracy.",
                  section: "Results",
                  page: 5,
                },
              ],
              relevance: "The clearest method result in a large candidate set.",
            },
            {
              id: "cv-local",
              title: "Do Vision Transformers Still Need Local Features?",
              authors: ["Adewale Adeyemi"],
              date: "2026-09-23",
              venue: "ICCV",
              doi: null,
              arxivId: "2609.14420",
              action: "deep_read",
              type: "application",
              relevance: "high",
              abstractOnly: false,
              citationCount: 1,
              problem:
                "Recent detectors are written up as transformers, while the stem still extracts the local features the transformer is praised for replacing.",
              contribution:
                "An ablation across three detectors showing the accuracy drop when that stem is removed.",
              method: "Same training recipe, stem replaced with a linear patch embed.",
              datasets: ["COCO"],
              benchmarks: ["COCO"],
              results: ["Removing the stem cost more accuracy than swapping the transformer block."],
              strengths: ["The comparison uses the authors' own code where it was available."],
              limitations: ["Three detectors is a sample, not a survey."],
              claims: [
                {
                  text: "Removing the stem cost more accuracy than swapping the transformer block.",
                  section: "Ablations",
                  page: 4,
                },
              ],
              relevance: "It changes how the token-merging result should be read.",
            },
            {
              id: "cv-occ",
              title: "OpenOcc: An Occupancy Benchmark with Honest Splits",
              authors: ["Priya Nair", "Chris Bell"],
              date: "2026-09-21",
              venue: "NeurIPS Datasets",
              doi: "10.48550/arxiv.2609.13330",
              arxivId: "2609.13330",
              action: "deep_read",
              type: "benchmark",
              relevance: "medium",
              abstractOnly: false,
              citationCount: 0,
              problem:
                "Occupancy papers test on scenes that overlap their training drives.",
              contribution:
                "A split that keeps whole drives on one side, plus a table of how published numbers move when the overlap is removed.",
              method: "Re-evaluation. No new model.",
              datasets: ["OpenOcc"],
              benchmarks: ["OpenOcc honest split"],
              results: ["Three published gains shrank once overlapping drives were removed."],
              strengths: ["The drive list is public."],
              limitations: ["It does not propose a better model, only a fairer number."],
              claims: [
                {
                  text: "Three published gains shrank once overlapping drives were removed.",
                  section: "Re-evaluation",
                  page: 3,
                },
              ],
              relevance: "A dataset result worth keeping beside the method papers.",
            },
            {
              id: "cv-drift",
              title: "Calibration Drift in Long-Running Camera Fleets",
              authors: ["Marc Duval"],
              date: "2026-09-19",
              venue: "arXiv",
              doi: null,
              arxivId: "2609.12008",
              action: "summarize",
              type: "application",
              relevance: "medium",
              abstractOnly: true,
              citationCount: 0,
              problem: "A detector that was calibrated in June is still running in September.",
              contribution:
                "A report of calibration drift on a fleet of fixed cameras, known from the abstract only.",
              method: "Not available. No legal PDF was found.",
              datasets: [],
              benchmarks: [],
              results: [],
              strengths: [],
              limitations: ["Abstract only. It is not evidence in the weekly findings."],
              claims: [],
              relevance: "The gap it points at is real. The card itself is a skim.",
            },
          ],
        },
      ],
    },
  ],
};

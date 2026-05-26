# Query Examples and Concept Mapping

This file contains representative counseling questions and the key concepts the agent should retrieve or surface when answering. Use this for retrieval alignment and to reduce hallucination.

Example 1
Q: "IIT Mandi EE vs Mechanical for software?"
Concepts:
- software flexibility
- circuit branch advantage (EE hardware→embedded)
- coding effort required (DSA timeline)
- placement optionality and recruiter pools

Example 2
Q: "Which branch gives safest chance of placement?"
Concepts:
- recruiter pool size
- internship pipeline
- median vs average packages
- batch size effects

Example 3
Q: "I want PSU and not software — which branch?"
Concepts:
- PSU domain mapping (power→EE, manufacturing→ME)
- GATE preparation and core course strength
- internship experiences relevant to PSUs

Example 4
Q: "How hard is it to switch from ME to software?"
Concepts:
- core-to-software transition recipe (DSA + projects + timeline)
- recruiter eligibility for ME grads
- realistic case studies (internship->offer path)

Example 5
Q: "Should I pick CSE or DSE?"
Concepts:
- software vs data specialization
- recruiter target roles and optionality
- coursework and project signals

Agent usage
- For each incoming user query, match to these templates; ensure retrieved docs cover listed concepts before synthesizing a final answer. If key concepts missing in retrieval, ask a short clarifying question instead of guessing.

End.

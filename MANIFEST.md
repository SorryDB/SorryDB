# SorryDB and Leaderboard

This project aims to stimulate the development of AI end-user that can assist mathematicans in proving theorems in Lean, by building a continuously updating benchmark and competition based on not-yet-formally-proven statements in public ongoing Lean projects.

## Background

### Benchmarks for automated theorem proving



### Competition math versus research math

Proving a theorem (or lemma) in research mathematics may consist of widely different tasks such as:

1. Computing (algebraically, numerically, ...)
2. Finding and applying relevant results in the literature
3. Using deductive techniques such as induction, case distinction, generalization, ...
4. Building new theory or abstraction
5. Constructing examples and counter-examples

### Last mile from ML paper to end product


## Measuring progress using unfinished proofs from public repositories

### Examples of sorry statements in Lean repositories



### Using sorry statements as benchmark problems

Compare with SWE-Bench [1], which aims to evaluate language models on real-world software engineering tasks by using GitHub issues as a benchmark.

Advantages:

1. Captures a wide range of different aspects of research mathematics
2. Being able to fill a sorry in an ongoing formalization projection is almost by definition something that is useful to someone
3. Having a constant influx of *new* sorries mitigates the problem of data contamination


### A continuously running leaderboard


Relative in stead of absolute performance


## References

1. Jimenez, C. E., Yang, J., Wettig, A., Yao, S., Pei, K., Press, O., & Narasimhan, K. (2023). SWE-bench: Can Language Models Resolve Real-World GitHub Issues? arXiv:2310.06770. https://arxiv.org/abs/2310.06770

2. Kumarappan, A., Tiwari, M., Song, P., George, R. J., Xiao, C., & Anandkumar, A. (2024). LeanAgent: Lifelong Learning for Formal Theorem Proving. arXiv:2410.06209. https://arxiv.org/abs/2410.06209

3. Rute, J. (2025). The last mile [Video]. Lean Together 2025. https://www.youtube.com/watch?v=Yr8dzfVkeHg





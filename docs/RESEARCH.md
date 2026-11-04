# Research behind the design

The sources that shaped Cueon, and what we did with each. Pilot data from Cueon itself doesn't exist yet.

## The problem

| Finding | Source | What it means for Cueon |
|---|---|---|
| Social stress (TSST) impairs free recall of learned material (n=29) | [Merz et al. 2010](https://www.cog.psy.ruhr-uni-bochum.de/cog/mam/paper/2010/merz_stress_socialmemoryretrieval_behavneurosci2010.pdf) | Show a cue to recognize, instead of asking the presenter to recall |
| Sentence recognition in quiet: 99.6% native, 70.7% Chinese listeners in the US, 41.0% in China | [Guan et al. 2021](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2021.631060/full) | Show the heard question on the lens |
| 30% of early-career researchers in Japan and Spain avoid English-language conferences | [Amano et al. 2023](https://www.timeshighereducation.com/news/non-native-english-speaking-scientists-profound-disadvantage) | Researchers are a target group |
| The question type a VC asks, and the framing of the answer, is linked to funding | [Kanze et al. 2018](https://business.columbia.edu/insights/chazen-global-insights/closing-gender-gap-startup-funding) | The answer's framing matters, not only the facts |
| ASR word error rates differ widely by speaker | [Koenecke et al. 2020](https://5harad.com/papers/asr-disparities.pdf) | A one-word or unsure transcript asks the speaker to repeat |

We found no reliable statistic for how often speakers freeze in Q&A.

## Time budget

| Finding | Source | What it means for Cueon |
|---|---|---|
| Turn gaps vary by about 250 ms across languages | [Stivers et al. 2009](https://forms.mpi.nl/node/50939) | People expect a fast reply everywhere |
| Silences 0.6 to 1.2 s longer are judged negatively | Roberts et al. 2006 | A stalling phrase and fallback card appear at once |
| Over 90% of users accepted a 2.8 s delay on smart glasses (n=20, preprint) | [SocialMind 2024](https://arxiv.org/pdf/2412.04036) | Target of 1.5 s p50, 2.5 s p95 |
| Agent replies over 4 s are rated worse | [Maslych et al. 2025](https://www.eecs.ucf.edu/isuelab/publications/pubs/maslychmCUI25.pdf) | New questions are still over this: see [results](results.md) |

The Voice Transcribe figure Meta publishes is about 0.16 s from end of speech to final transcript.

## Reading on the lens

| Finding | Source | What it means for Cueon |
|---|---|---|
| Ray-Ban Display: 600 by 600, right eye, about 20 degrees, 42 px per degree | [UploadVR review](https://uploadvr.com/meta-ray-ban-display-review), [Meta docs](https://wearables.developer.meta.com/docs/develop/webapps/build/display-and-layout/) | One fixed card layout, high contrast |
| A glance is about 2 s, roughly 4 to 5 words (our estimate); simple numbers read within 300 ms | [NHTSA](https://www.nhtsa.gov/sites/nhtsa.gov/files/811781.pdf), [Blascheck et al.](https://www.microsoft.com/en-us/research/uploads/prod/2018/08/GlanceableVis-InfoVis2018.pdf) | First line of 12 words or fewer, numbers first |
| Reading and speaking compete for language resources | [Wickens](https://interruptions.net/literature/Wickens-HF08.pdf) | Cards are for glancing before answering, and dim after 10 s |
| Line scrolling is faster than one-word flashing on smart glasses; top-right placement scores worst | [Rzayev et al. 2018](https://teaching.vda.univie.ac.at/hci/20s/materials/Lit-Tests/LT2-Rzayev2018.pdf) | Normal lines of text, on the display's own position |
| 68% of respondents wanted bullet points and one example sentence (n=20, preprint) | [SocialMind 2024](https://arxiv.org/pdf/2412.04036) | First line plus short points |

## Why not the glasses microphone

Glasses web apps can't use the microphone, and the glasses' Bluetooth mic is beamformed toward the wearer, which
suppresses the audience ([Meta docs](https://wearables.developer.meta.com/docs/develop/dat/microphones-and-speakers/)).
So audience speech comes from a laptop, phone or pin mic.

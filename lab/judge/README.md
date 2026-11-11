# The judge: a local vision model that answers fixed questions

This folder measures whether a small vision model on a local machine can tell the pilot several times a second what the frame shows, with fixed questions, fixed answers and a probability for each answer. The numbers and what follows from them are in `docs/LOG.md` under 11 November.

`sample.py` draws 210 frames from the recordings into `sample/` (JPEGs, not in the repository) and writes `sample.json` with what the readers say about each: the screen, the minimap class, the wanted level. `truth.json` corrects the one thing the readers get wrong, how the figure moves, by hand from contact sheets of all 210 frames. `measure.py` asks a model on any OpenAI-compatible server its questions about every frame and writes the answers, their log-probabilities and the times to `results/`. `disagreements.py` lists the frames on which a result and the readers differ and puts them on one sheet to look at.

The first set of questions (`results/v1/`) asked for one situation out of five and is kept as the reason for the second: a phone can be open while the figure stands on foot, and the model then has to pick one. The questions now are independent of each other.

To repeat a measurement, with the frames in place and the model loaded on the server:

    pilot/.venv/bin/python lab/judge/measure.py --url http://<server>:1234 --model qwen/qwen3-vl-8b --width 640 --joint

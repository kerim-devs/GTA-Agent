# P63: A policy on the gaming PC: a model that turns frames into pad states, timed where it runs

## Why

The reaction bench of P62 compares ways of control, and one of them is a model that takes the frame and gives the gamepad, with no reader, rule or question in between. NitroGen is the only open model of that kind with weights and a server in its repository, and the plan has had it down as an experiment since 11 November. What decides whether it can play is not published: its paper leaves real-time use to future work and names no time per request, no memory, and not whether GTA V was among its games. Open-P2P is the second candidate, trained and run at 20 Hz. See the log of 12 November, "Ways of control", for the sources.

This card is carried out by the reviewer over SSH and not by a worker: the work happens on the gaming PC, and the Mac's disk was full when it was written.

## Limits on the gaming PC

The PC belongs to a colleague. Everything goes into Kerim's account `gta` and under one folder, `C:\Users\gta\policy\`, which can be removed as a whole: the Python, the environment, the repository, the weights. Nothing is installed for the machine, nothing starts by itself after a restart, and no firewall rule is asked for.

NitroGen's server unpickles whatever it is sent and binds to every interface as published. Here it listens on `127.0.0.1` only, and the Mac reaches it through a forwarded port of the SSH connection it already has. The same holds for any other server of this card.

The judge shares the card. Before and after every measurement the judge's own answer time is read, and a policy that slows the judge beyond half a second an answer does not run beside it.

NitroGen's licence is non-commercial. Timing it is covered by the plan; whether it may play in a public stream stays Kerim's decision, and nothing here depends on the answer.

## What to do

Set up. A Python of its own under the folder (uv, installed for the user), torch with CUDA, the repository at a pinned commit, the weights from Hugging Face. If the weights ask for an account or a token, stop there and say so: a token is Kerim's to give. Note every command in the report so that the folder can be rebuilt.

Time it on the PC, with no network in the way: the seconds until the model is loaded, the memory it takes beside the loaded judge, and the time for one request, one frame in and one chunk of actions out, over 200 requests after a warm-up: median, ninth decile, worst. The same with fewer flow steps where the code allows it (16, 8, 4), with what the chunk loses. Say how many actions of a chunk are meant to be played before the next request and at which rate, from the code, not from the paper.

Time it from the Mac through the forwarded port, with frames of Kerim's recordings scaled as the model wants them, the same three numbers, and the judge's answer time alone and beside the running policy.

Look at what it presses. On ten stretches of Kerim's recordings of ten seconds each, three of them from fights, put its pad states beside his: the share of ticks on which the left stick points within 45 degrees of his, and whether it aims or fires where he does. The plan's bar for calling it usable is eight of ten clear steering moments.

Hand it to the bench. Once P62 is merged, the `policy` entry of `approaches.py` sends the frame through the forwarded port and plays the chunk at the model's rate until the next one arrives; its reaction on the scenes is then measured like every other way of control.

Open-P2P follows the same steps when NitroGen cannot be loaded, needs more than the free memory, or takes longer than 100 ms a request. Its weights carry no stated licence, which the report says where its numbers appear.

## Done when

The log has the numbers with how each was taken, the report has the commands that build the folder, start the server and stop it, and it says in one sentence each whether the model is fast enough to act, whether it plays GTA V at all, and whether `policy` goes into the reaction bench.

# Packet Predator: a beginner's guide

This guide is for someone who has never used Packet Predator, worked with radio modules, or looked at computer messages before. You do not need to understand programming or hexadecimal numbers to begin.

## The short explanation

Suspicious Cellmates uses several electronic devices. Player devices, task stations, effects such as lights, and the Game Controller eventually need to send short messages to one another.

Imagine that every message is a tiny labelled envelope. The outside says who sent it, where it is going, and what kind of message it is. The inside contains the details.

**Packet Predator is the workbench where we examine and test those envelopes.** It can:

- open a known example and explain it in ordinary language;
- show exactly who sent a message and who should receive it;
- show the individual values and bytes inside it;
- replay a short, fixed list of example messages;
- notice malformed or unexpected messages; and
- when deliberately connected to a supported radio, receive a real message or transmit one chosen message.

Packet Predator is mainly a development and troubleshooting tool. It helps us build and test the other devices. It is not the software that runs a game.

## The wider system, told as a story

Suppose a new Player Node has just been switched on. It wants the Game Controller to know that it exists.

The Player Node prepares a **Node hello** message using the shared rules in the **Protocol Contract**. A transport, perhaps an nRF905 radio, carries that message. The Game Controller receives it and decides what should happen next.

Packet Predator can sit at the workbench and help us inspect this exchange. It might show:

> A node at address 7 sent a Node hello message to the Game Controller at address 0.

It can then reveal the exact fields and bytes for someone diagnosing a problem. Packet Predator explains what arrived, but it does not decide whether the player may join the game. That decision belongs to the Game Controller.

The main parts have different jobs:

- The **Protocol Contract** is the shared dictionary and rulebook for messages.
- **Packet Predator** is the magnifying glass and test bench for those messages.
- The **Game Controller** is the referee that runs the game and makes automatic game decisions.
- The **Game Master Console** is the live operator's control panel. It asks the Game Controller to perform deliberate interventions during a game.
- **Nodes** are the physical devices used by players, tasks, or room effects.

Keeping these jobs separate makes testing safer. Opening Packet Predator will not unexpectedly start a game, invent simulated players, or make decisions on their behalf.

## What you will see

Packet Predator opens as a webpage in an ordinary browser. The top-right status tells you how it is currently operating.

### `Inspect only · no radio`

This is the normal and safest starting mode. You can examine examples and play recordings, but the computer cannot send anything over a radio.

### `Live nRF905`

Packet Predator was deliberately started with a radio configuration. The
server listens for real frames continuously, including while no browser is
open. The page subscribes to the server's temporary observation model rather
than asking the radio to check for one frame at a time. It can transmit only if
transmission was also enabled in that configuration, and the person using the
page confirms each transmission individually.

### `Contract 1.x.x`

This means Packet Predator found the shared message rulebook. The number identifies the version it is using. If the page says **Contract unavailable**, the two project folders may not be in the expected places.

### Reading the live-radio screen

When Packet Predator starts with a physical radio, the page keeps the live
workflow together. The nRF905 status and deliberate transmit controls appear
first. The currently inspected, transmitted, or received frame appears
immediately below them, followed by **Recently inspected**. The manual
hexadecimal editor and deterministic recording player come afterward as
secondary tools.

The large frame heading uses the exact protocol symbol, such as
`HELLO_RESULT`, so it can be compared directly with logs, fixtures, and source
documentation. The surrounding sentence still explains the message in
ordinary language.

Use **Text size** in the top bar to choose **Comfortable**, **Large**, or
**Extra large**. Large is the default. Use **Typeface** to choose **Sans** or
**Monospace**. Packet Predator remembers both choices in the current browser.

## Your first five-minute tour

Start without a radio. This lets you learn the screen without transmitting anything.

1. Open Packet Predator in your browser.
2. Find **Choose your first frame** and select **Node hello**.
3. Read the sentence beneath the message name. It gives the quickest explanation of the message.
4. Look at **From** and **To**. This is the route the message is allowed to take.
5. Open the **Overview** tab to see who may send and read this kind of message.
6. Open **Fields** to see the named pieces of information carried inside it.
7. Open **Bytes** to see the exact computer representation.

You do not need to understand the byte view to use Packet Predator. It exists so a developer can answer questions such as, “Did the radio change a byte?” or “Did both programs build the same message?”

Every valid selected frame also opens as an **Editable draft**. Change an
address or named value in **Fields** when you know the protocol meaning, or
change a two-digit cell in **Bytes** when you need exact control. The other
view updates after Protocol Contract validates the edit. Changed bytes receive
an amber marker, and focusing a field highlights its bytes.

**Undo**, **Redo**, and **Revert** keep the original fixture or observation
intact. If a byte edit makes the frame invalid, Packet Predator preserves the
draft and explains the codec error, but disables transmission until you undo,
revert, or correct it. Choosing another frame while a modified draft is open
requires confirmation.

The list on the left contains other known-good examples. Selecting one loads and inspects it immediately. The search box helps find an example by its name or family.

## Playing a recorded exchange

A recording is a short, prewritten sequence of messages. Think of it as a packet slideshow.

For example, **Node onboarding** demonstrates a few messages associated with a node appearing and being configured. Select the recording and then use:

- **Step** to reveal exactly one message;
- **Play** to follow the recorded timing;
- **Pause** to stop at the current point;
- **Reset** to return to the beginning; and
- **Speed** to play the same recording faster or slower.

This is not a simulated game. The recording cannot think, branch, choose an outcome, or reply to anything you do. It always presents the same known messages in the same order.

If the display says **Recorded outbound**, that only describes the direction written in the recording. Your computer did not actually transmit it.

## Looking at a message someone gives you

A developer may give you a line of characters such as:

```text
46 07 00 01 01 00 E8 03 00 00
```

This is a message written in **hexadecimal**, a compact way of displaying computer bytes.

1. Paste the text into **Paste bytes or use an example**.
2. Leave **Interpret as** set to **Detect logical or 32-byte frame** unless a developer asks for something different.
3. Select **Inspect frame**.
4. Read the explanation, route, and fields that appear below.

If the message is incomplete or breaks the shared rules, Packet Predator displays an error rather than guessing. Give the error name and message back to the developer who supplied the bytes.

## The inspection journal

Every message you inspect during the current run appears under **Recently inspected**. Selecting an entry opens it again.

This journal is temporary. It is cleared when Packet Predator stops, and it is not yet a permanent game record. If you need to preserve something important, copy the text or take a screenshot before stopping the program.

## Starting Packet Predator on an already prepared computer

Open a **terminal**. A terminal is simply a window where you type instructions instead of clicking icons.

If Packet Predator is installed in the usual place, copy and paste these lines:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/run-local
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser on that same computer.

To stop Packet Predator, return to the terminal and press `Ctrl+C`. This means hold the Control key and press C once.

### If this is the first run

The preparation command only needs to be run when Packet Predator is first installed or its requirements change:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/setup-local
```

After it finishes, use `./scripts/run-local` as shown above.

If the project was installed somewhere else, ask the person who prepared the computer for its folder location.

## Using Packet Predator on a prepared Raspberry Pi radio bench

The two-Pi bench is for deliberately proving that two nRF905 modules can exchange one exact message at a time. It is not a complete game network.

On a Pi that has already been wired, configured, and tested, Packet Predator is started with its local radio profile:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/run-rpi config/nrf905-bench.local.json
```

A prepared Pi can instead install the tracked boot service once, after which
Packet Predator starts without a dedicated terminal:

```sh
./scripts/install-systemd-service config/nrf905-bench.local.json
./scripts/systemd-status
```

See [unattended Packet Predator startup](docs/systemd-deployment.md) for the
one-time safety checks and routine update commands. Do not use the manual and
systemd startup methods at the same time.

By default, the webpage remains private to that Pi. From another computer, an SSH connection can safely carry the page to a local browser port. For Pi A, a prepared bench might use:

```sh
ssh -L 8001:127.0.0.1:8000 your-user@packet-predator-a.local
```

Keep that terminal open and visit [http://127.0.0.1:8001](http://127.0.0.1:8001). Replace `your-user` with the username created while setting up the Pi.

When a real frame arrives, the server puts it in the temporary observation
model immediately. An open browser receives a live notification and shows it
in the inspection view and journal. Closing or reconnecting the browser does
not stop or slow radio reception, and Packet Predator does not automatically
reply.

The live-view connection and the radio receiver are separate. If the page says
that its live view is reconnecting, the Pi continues listening and the page
resynchronizes from the retained journal when its connection returns.

If radio bytes pass the hardware address and CRC checks but do not form a valid
Protocol Contract message, Packet Predator retains their exact hexadecimal
bytes and shows a structured decode error. One bad frame does not stop later
valid frames from being captured.

To send a frame from the browser:

1. Choose a known example or paste the requested frame.
2. Check that the route and meaning are the ones you intend to test.
3. Tick **Confirm one RF transmission**.
4. Select **Transmit current frame**.

The confirmation applies to one transmission only. It must be ticked again before sending another message.

Radio setup, wiring, diagnostic commands, and the exact two-way test are explained separately in [the nRF905 two-Raspberry-Pi bench guide](docs/nrf905-two-pi-bench.md). Have someone comfortable with electronics complete that preparation. Always power the Pi off before changing wires, use the correct antenna, and never connect an unverified module to 5 volts.

## What happens when the radio test runs

The diagnostic script is not secretly deciding what bytes a message should contain. It works through a chain in which each part has one job.

Suppose you ask it to send the official **Controller beacon** example. Packet Predator goes to the sibling Protocol Contract repository and finds that released fixture. The reference codec reads the contract's registry, checks the fixture, and rebuilds the message using the registered layout. Because the nRF905 carries fixed 32-byte blocks, blank zero bytes are added after the meaningful message until it is exactly 32 bytes long.

The radio adapter then receives those 32 bytes without knowing that they mean “Controller beacon.” It writes them into the nRF905 and asks the hardware to transmit. The radio adds its own CRC error check on air; those CRC bits sit outside the 32-byte application message.

At the other Pi, the nRF905 accepts traffic matching its physical radio address and CRC. Packet Predator reads the resulting 32 bytes. Before trying to explain anything, the diagnostic compares every received byte with the official fixture it expected. One changed byte makes the test fail.

Only after all bytes match does the reference codec decode the message. It reads the small envelope to learn the wire generation, payload length, message type, logical sender, and logical recipient. The registered message type selects the one permitted payload layout, and the codec converts each little-endian sequence of bytes into its named numeric value. Packet Predator then adds friendly labels such as **Game Controller**, **Node endpoint 1**, and **Controller beacon** for display.

This separation is deliberate:

- the Protocol Contract defines the bytes and their meaning;
- the reference codec translates between those definitions and bytes;
- the nRF905 adapter moves an opaque 32-byte block;
- the diagnostic proves the block was unchanged; and
- Packet Predator presents the decoded result.

The successful 2026-07-24 test is recorded in [the physical validation result](docs/nrf905-validation-2026-07-24.md). The bench guide also breaks the successful Controller beacon down byte by byte.

## Keeping a prepared Pi up to date

Packet Predator and the Protocol Contract are stored in Git repositories. Git lets the Pi download reviewed development changes without copying files manually.

After the repositories have been connected to their shared Git remotes, update a Pi with:

```sh
cd ~/Suspicious_Cellmates/Packet_Predator
./scripts/update-rpi
```

The updater downloads both repositories, applies only straightforward updates, refreshes the Pi's Python environment when its requirements changed, and runs the project checks. It refuses to overwrite source files changed directly on the Pi. The Pi's ignored `config/nrf905-bench.local.json` radio profile is left alone.

Packet Predator does not restart automatically. This gives you a chance to read the check result before starting it again.

## Things Packet Predator does not currently do

Packet Predator does not:

- start, stop, or run a Suspicious Cellmates game;
- decide player roles, task outcomes, kills, meetings, or sabotage;
- act as the Game Master Console;
- create imaginary players or nodes that respond automatically;
- save a permanent game history;
- discover and configure radios automatically; or
- provide a login when deliberately exposed to a local network.

The nRF905 support is experimental. A successful bench test means those two radios exchanged the expected bytes with the chosen settings. It does not yet prove that nRF905 is the final radio for the project.

## Common questions

### Can I break a game by clicking an example?

Not in **Inspect only** mode. Choosing and inspecting an example does not transmit it. In radio mode, transmission still requires an enabled local profile and a fresh one-shot confirmation.

### Do I need to learn hexadecimal?

No. Start with the plain-language message title, summary, route, and field labels. The exact hexadecimal view is available when a developer needs it.

### Does **Play** send messages over the radio?

No. The recording player feeds fixed examples into Packet Predator's inspection screen only.

### Why are some messages shorter than 32 bytes?

The meaningful message may be short, much like a short note placed in a standard-sized envelope. The nRF905 bench carries a fixed 32-byte block, so unused space is filled with zeros. Packet Predator calls these unused bytes **padding**.

### Why can I see two meanings for the word “address”?

A logical endpoint address identifies a participant in the message system. The nRF905 also uses a physical radio address to decide which radio traffic to accept. Packet Predator keeps these ideas separate even though both are commonly called an address.

### Why did my recent messages disappear?

The current journal lives only in memory. Stopping or restarting Packet Predator clears it.

### Can I open the Pi's webpage directly over Wi-Fi?

It is possible on a trusted development network, but the current page has no login. SSH forwarding, as shown above, is the safer default. Never expose Packet Predator directly to the internet.

## Glossary

**Adapter**  
A piece that connects Packet Predator to a particular way of moving messages. The current physical adapter is experimental support for nRF905 radios.

**Address**  
A number used to identify where a message came from or where it should go. A radio may also have a separate physical address used only for radio reception.

**Byte**  
A small unit of computer data. Packet Predator can show every byte so two messages can be compared exactly.

**Capture**  
A message observed as it arrives from a transport, such as a radio.

**Channel**  
One selectable radio frequency setting. Two nRF905 radios need compatible settings to hear one another. The appropriate setting must also comply with local radio rules.

**Codec**

A translator between named message fields and their exact byte representation. “Encoding” builds bytes; “decoding” reads bytes back into fields. Packet Predator uses the sibling Protocol Contract's reference codec.

**Contract example or fixture**  
A known-good sample message published with the Protocol Contract. These examples give every program a shared answer to compare against.

**Deterministic**  
Guaranteed to happen the same way each time. A deterministic recording contains the same messages, order, and timing whenever it is replayed.

**Device Tree overlay**

A Raspberry Pi boot setting that describes or adjusts how Linux should use hardware and GPIO pins. The original nRF905 HAT uses one to release GPIO7 from an unused second SPI chip-select.

**Environment Node**  
An optional device that creates room effects, such as lights or a siren. These nodes are not required for the first playable version.

**Field**  
One named piece of information inside a message, such as a status, reason, difficulty, or counter.

**Frame**  
One complete message in the form carried or inspected by the system. In everyday discussion, this project often uses “frame” and “packet” for nearly the same thing.

**Game Controller**  
The authoritative program that runs the game, keeps game state, applies rules, and coordinates devices. Packet Predator is not the Game Controller.

**Game Master Console**  
The trusted live control panel used by the person running a game. It asks the Game Controller to perform actions such as handling a failed task station or applying a deliberate intervention. It is not Packet Predator.

**GPIO**

A controllable electrical pin on the Raspberry Pi. Packet Predator uses several GPIO pins to power the radio, select transmit or receive mode, and read status signals.

**Hardware CRC**

An error-detection value added and checked by the nRF905 itself. It helps reject radio frames damaged in transit and is not part of the 32-byte protocol message.

**Hexadecimal or hex**  
A compact way to write bytes using the digits 0–9 and letters A–F. For example, decimal 15 is written as `0F` when displayed as one byte.

**Inspect only**  
Packet Predator's safe default mode. It can explain examples or pasted messages, but it has no live radio and cannot transmit.

**Journal**  
The list of messages inspected during the current Packet Predator run. The present journal is temporary and clears when the program stops.

**Logical frame**  
Only the meaningful message bytes: its small header and its actual contents. A fixed-width adapter may add padding before carrying it.

**Message type**  
The label that tells readers what kind of message this is and therefore how to interpret its contents, such as **Node hello** or **Task outcome**.

**nRF905**  
The inexpensive radio module currently being tested as Packet Predator's first physical adapter. It is experimental rather than a permanent platform decision.

**Node**  
A device that participates in the system. The main planned kinds are Player Nodes, Task Nodes, and Environment Nodes.

**Packet**  
A small, structured block of data sent between system participants. Think of it as a tiny labelled envelope. See also **Frame**.

**Packet Predator**  
The developer workbench used to inspect, explain, replay, capture, and deliberately transmit test messages. It does not run the game.

**Padding**  
Unused zero bytes added when a transport needs a fixed-sized frame. They are blank space, not additional game information.

**Player Node**  
A device carried or worn by a player. Its exact hardware and game behaviour are developed separately from Packet Predator.

**Profile**  
A local configuration file describing the attached hardware and its radio settings. Packet Predator will not start a physical radio unless a profile is deliberately supplied.

**Protocol**  
The agreed rules that let different programs and devices understand one another's messages.

**Protocol Contract**  
The project's authoritative, shared definition of message names, values, layouts, and known-good examples. Packet Predator reads this contract instead of inventing its own message rules.

**Raspberry Pi**  
A small Linux computer. The first physical Packet Predator bench uses two Raspberry Pi 5 computers, each attached to an nRF905 module.

**Recording or replay**  
A finite list of known messages and timings used to reproduce an exchange on the inspection screen. It is a packet slideshow, not an intelligent simulation.

**Route**  
The journey described by a message's source and destination: who sent it and who should receive it.

**SSH**  
A secure way to open a terminal on another computer over a network. It can also carry the Pi's private Packet Predator webpage to your own computer.

**SPI**

The short wired connection used by the Raspberry Pi to configure the nearby nRF905 and move payload bytes into or out of it. SPI speed is separate from radio frequency and over-air data rate.

**Task Node**  
A physical task station that players interact with. The Task Node is responsible for deciding when its own task has been successfully completed and reporting that outcome to the Game Controller.

**Transport**  
The method used to move a complete message. A radio, a recording player, a file, or a future wired connection can all be transports.

**Workbench**  
A tool used while building, examining, or repairing something. Packet Predator is a software workbench for messages.

## Where to go next

- For a little more technical detail about using a normal computer, read [Laptop workbench](docs/laptop-workbench.md).
- For radio wiring and the exact two-Pi validation procedure, read [nRF905 two-Raspberry-Pi validation bench](docs/nrf905-two-pi-bench.md).
- For the precise project boundaries and current development status, read the main [README](README.md).

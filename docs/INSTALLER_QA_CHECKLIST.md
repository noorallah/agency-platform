# Installer round 1: QA checklist

For the person testing `AgencyPlatform-1.0.0-Setup.exe` on a laptop. This is
the first time the installer runs on a real PC, so the aim is to find where
what happens differs from what the installation guide
(`INSTALL_GUIDE.md`, shipped as *Installation guide.html*) says. Follow the
guide step by step and record every difference, however small.

Written 2026-09-24 from the installer as built that day. Update the Expected
column when the product changes, and the Result and Notes columns as you test.

## How to test

**You need**

- A laptop you can wipe: 64-bit Windows 10 or 11, at least 4 GB of memory,
  3 GB free disk, no PostgreSQL on port 5433, and an administrator account.
  No internet is needed.
- A second PC on the same network for section C. A second Windows user on the
  laptop is not a substitute, because the app-only role is a separate install.
- `AgencyPlatform-1.0.0-Setup.exe` and the installation guide, both from the
  developer.

**On every failure, capture three things**

1. A screenshot of the screen as it was, including any message.
2. The newest file in `C:\ProgramData\Agency Platform\logs\install`, and for
   anything after install, the folder the guide's *Which log to read* table
   names.
3. The version shown on the app's sign-in screen.

**Recording results.** Set each case's Result to `Pass`, `Fail` or `Blocked`,
and write in Notes what you saw when it was not exactly what the Expected
column says. A case that passed with different wording or an extra click is
still worth a note. `Blocked` means an earlier failure stopped you reaching it.

Run the sections in order: A, B, C, then D. Section D ends with the laptop
uninstalled, so it comes last.

## A. Server laptop

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| A1 | Double-click `AgencyPlatform-1.0.0-Setup.exe` | SmartScreen shows *Windows protected your PC*; **More info** then **Run anyway** goes on. Then an administrator prompt | Not run | |
| A2 | Welcome page | Names *Agency Platform 1.0.0* | Not run | |
| A3 | Destination page | Defaults to `C:\Program Files\Agency Platform` | Not run | |
| A4 | *This PC* page | Two choices, **This PC: server and app** preselected, tick box *Allow other PCs on this network to connect* enabled | Not run | |
| A5 | Pick **App only**, then back to **server** | The tick box greys out for app only and comes back for server | Not run | |
| A6 | Keep **server**, tick *Allow other PCs*, Next | No *Server* address page appears. Shortcuts page with *Create a desktop shortcut* ticked | Not run | |
| A7 | **Install** | Files copy, then *Setting up the database and the server. This can take a few minutes.* Under five minutes in all | Not run | |
| A8 | Finished page | Says the server is running as a Windows service. Shows *Sign in with*, `platform-admin@agency.local`, a password, a **Copy** button, and *Launch Agency Platform* ticked | Not run | |
| A9 | **Copy**, paste into Notepad | Two lines, *Sign in as* and *Password*, matching the page; the button reads *Copied* | Not run | |
| A10 | **Finish** | The app opens: a brief *Connecting to server…* then the sign-in screen | Not run | |
| A11 | Start menu, *Agency Platform* folder | Entries *Agency Platform*, *Agency Platform logs*, *Installation guide*, *Uninstall Agency Platform*; a desktop shortcut too | Not run | |
| A12 | Open `C:\ProgramData\Agency Platform` | Folders `pgdata`, `logs`, `backups`, `storage`; `first-login.txt` opens only as administrator and holds the same sign-in | Not run | |
| A13 | Open `logs` | Subfolders `install`, `server`, `service`, `database`, `client`; `install` holds one file for this run | Not run | |
| A14 | Open **Services** (type *services* in Start) | *Agency Platform Database* and *Agency Platform Server* both *Running*, startup *Automatic* | Not run | |
| A15 | Windows Defender Firewall > Advanced settings > Inbound Rules | A rule *AgencyPlatformServer-TCP-8000*, enabled, for private networks | Not run | |

## B. First use on the laptop

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| B1 | Sign in with the copied account | A change-password dialog opens at once; the app cannot be used until it is done | Not run | |
| B2 | Try `Short1!` as the new password | Refused: at least 12 characters with upper, lower, digit and symbol | Not run | |
| B3 | Try the old password again as the new one | Refused: may not repeat a recent password | Not run | |
| B4 | Set a valid new password | Accepted; the app opens on its home screen with no firm | Not run | |
| B5 | Sign out, sign in with the **old** password | Refused | Not run | |
| B6 | Sign in with the new password | Works | Not run | |
| B7 | Type a wrong password five times | The account locks for 15 minutes with a message saying so | Not run | |
| B8 | Open **Firms**, create a firm with name, code, GST number and address | Created; it appears in the grid | Not run | |
| B9 | Open the firm's **Set up** panel | Lists what the firm still needs: open books, GST template, control accounts, default branch, each with a button | Not run | |
| B10 | Complete each Set up item | Each turns green; the panel reports the firm ready | Not run | |
| B11 | **Users**: create a user, give a role, add to the firm | Created; sign out and sign in as that user; the firm's screens open | Not run | |
| B12 | Open `logs\server` | A file for today, `server-<date>.log`, and an `errors-<date>.log`; the errors file is empty or nearly so | Not run | |
| B13 | Open `logs\client` | A folder named after your Windows user with `client-<date>.log` | Not run | |
| B14 | Sign-in screen, gear icon | *Application Settings* opens; **API URL** reads `http://127.0.0.1:8000`; **Open logs folder** opens `C:\ProgramData\Agency Platform\logs` | Not run | |

## C. Second PC, app only

Find the laptop's address first: `ipconfig` on the laptop, the *IPv4 Address*
line.

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| C1 | Run Setup on the second PC, past SmartScreen | Same as A1 | Not run | |
| C2 | *This PC*: choose **App only** | The tick box greys out; Next shows the *Server* page with `http://` prefilled | Not run | |
| C3 | Type a wrong address, e.g. `http://192.168.1.250:8000`, Next | A message: nothing answered at that address, check the address, the server PC and its firewall; *Use this address anyway?* Answer **No** | Not run | |
| C4 | Type `nonsense`, Next | Refused with an example of a valid address | Not run | |
| C5 | Type the laptop's real address with `:8000`, Next | Accepted without a warning | Not run | |
| C6 | **Install**, **Finish** | Fast; no *Setting up the database* wait. Finished page says it connects to that address and how to change it later. The app opens on the sign-in screen | Not run | |
| C7 | Sign in as the user from B11 | Works; the firm's screens open | Not run | |
| C8 | Check `C:\Program Files\Agency Platform` on this PC | No `backend`, `pgsql` or `service` folders; **Services** has no Agency Platform entries | Not run | |
| C9 | Sign-in screen, gear icon, set **API URL** to the wrong address from C3, Save, restart the app | *Connecting to server…* for up to a minute, then *The Agency Platform Server service is not running* with **Retry**, **Open logs folder**, **Continue to sign-in** | Not run | |
| C10 | **Continue to sign-in**, gear, set the right address back, Save | Sign-in works again | Not run | |
| C11 | On the laptop, stop *Agency Platform Server* in Services; on the second PC restart the app, then start the service again and click **Retry** | The connecting screen appears while the service is stopped; after Retry the app reaches sign-in | Not run | |

## D. Resilience, upgrade path and uninstall

| ID | Step | Expected | Result | Notes |
| --- | --- | --- | --- | --- |
| D1 | Restart the laptop, wait a minute, open the app | Both services are running again by themselves; sign-in works; data from B is there | Not run | |
| D2 | Run the same Setup again on the laptop | No *This PC* page; it installs into the same folder. Before copying, a *Backing up the database* step. Finished page says *upgraded to 1.0.0 … Sign in as before* and shows no password | Not run | |
| D3 | After D2 | `C:\ProgramData\Agency Platform\backups` holds a `pre-upgrade-1.0.0-<date>` folder with dump files; the firm and users are still there; the old sign-in still works | Not run | |
| D4 | Uninstall from *Add or remove programs* | Asks *Also delete all data (database, backups, logs)?* with **No** the default. Answer **No** | Not run | |
| D5 | After D4 | Program folder gone; no Agency Platform services; no firewall rule; `C:\ProgramData\Agency Platform` still there with `pgdata`, `logs`, `backups` | Not run | |
| D6 | Run Setup again, server role | Finished page shows **no** new password: *upgraded … Sign in as before*. Sign in with the password set in B4; the firm is there | Not run | |
| D7 | Uninstall again, answer **Yes** | `C:\ProgramData\Agency Platform` is gone as well | Not run | |
| D8 | Run Setup a third time, server role | A fresh install: a new password on the finished page; no firm | Not run | |
| D9 | On the second PC, uninstall | No data question is asked, or it is asked and answering either way leaves nothing behind but the user's own settings file | Not run | |

## Results summary

Fill in when all sections are done.

| | |
| --- | --- |
| Tester | |
| Date | |
| Laptop: Windows version, memory, free disk | |
| Second PC: Windows version | |
| Cases passed / failed / blocked | |
| Install log files sent | |
| Worst problem found | |

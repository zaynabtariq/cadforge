# Fusion workstation and terminal UI

VM lifecycle helpers, Autodesk sign-in through a local wrapper, and a terminal-browser workspace for viewing the resulting CAD model. The viewer includes a parts panel, hover/focus highlighting, camera presets, grid, and wireframe controls.

The repository contains source and configuration examples. Supply your own AWS account, Windows workstation, SSH keys, Autodesk account, and appropriate Fusion license. AWS resources are created only when you explicitly run the provisioning scripts or start a configured workstation.

## Configure an existing workstation

Requires Python 3.10+, AWS CLI, OpenSSH, `terminal-browser`, and a Windows EC2 instance with Autodesk Fusion installed. The native browser on Windows uses loopback CDP; the Fusion bridge uses loopback HTTP. Access to both is forwarded over pinned SSH.

```sh
python3 -m pip install -r fusion-workstation/requirements-auth.txt
cp fusion-workstation/auth-vm.example.json fusion-workstation/auth-vm.json
cp fusion-workstation/ssh_config.example fusion-workstation/auth-ssh_config
```

Fill `auth-vm.json` with your region, instance ID, and Windows user. Update `auth-ssh_config` with your SSH identity file, user, host-key alias, and known-hosts path. Obtain the server's public host key through a trusted channel such as your authenticated AWS SSM session and pin it in that known-hosts file. The runner resolves the current instance address through EC2; keep `StrictHostKeyChecking yes`.

The `fresh` target names the configured authentication workstation; it does not imply that its profile is empty. To also manage a primary workstation, copy `state.example.json` to `state.json` and create a separate `ssh_config` with the matching user and host key. Those live configuration files are ignored by Git.

AWS CLI credentials use the normal provider chain: environment, named profile, SSO, or instance role. Optionally set `FUSION_AWS_ENV_FILE` to an ignored env file containing AWS settings. No credentials file is loaded from an operator-specific default path.

## Windows setup source

`bootstrap.ps1` and `install.ps1` install the desktop software. `prepare-desktop.template.ps1` creates the initial Windows profile and expects an operator-supplied RSA public key in its template placeholder. `install-ssh.template.ps1` expects your SSH public key and a required `OperatorAddress` firewall argument. Render templates into the corresponding ignored filenames; inspect them before running as Administrator.

Package the supplied Fusion add-in with:

```sh
python3 fusion-workstation/package-bridge.py
```

The archive contains `FusionMCPBridge/`; install that directory in the Windows user's Fusion API `AddIns` directory and enable it. The source package includes the main-thread dispatcher, CAD handlers, and viewer snapshot handlers. It binds its bridge to loopback.

`prepare-auth-profile.ps1`, `begin-signin.ps1`, `dismiss-first-run.ps1`, and `remote-auth-policy.ps1` configure the dedicated `FusionAuth` Windows profile, native sign-in tasks, and browser policy. This profile setup disables the original `Fusion` account and restarts Fusion processes: use it on your dedicated setup or clone after preserving work. `bootstrap-auth-vm.py` applies these scripts to a configured clone with SSM and pins its regenerated SSH host key. It expects an existing private source setup and the generated bridge archive.

The provisioning helpers are also included. Copy `deployment.example.json` to `deployment.json` and set your VPC, subnet, region, and instance type before running `provision.py` followed by `launch.py`. These create billable AWS resources. `provision-auth-vm.py` optionally clones your private backup AMI, supplied as `image_id` in an ignored `backup.json`; it is a recovery/profile-testing tool, not a sanitized multi-user image builder. Keep backups containing native profiles private.

## Login and view in the terminal

From the repository root:

```sh
python3 fusion-workstation/workstation.py status --all
python3 fusion-workstation/workstation.py login --open
python3 fusion-workstation/workstation.py auth-status
python3 fusion-workstation/workstation.py verify
```

The wrapper shows the actual Autodesk sign-in step: email, password, MFA when requested, native product launch, then Fusion readiness. Enter credentials in the local wrapper. The broker forwards input only to the observed allowlisted Autodesk page on Windows. It distinguishes a restored session from a newly observed login; cached verification is not live proof.

The terminal-browser integration is in `workstation.py`, `terminal-auth-main.cjs`, and `connector-ui/`. The generated local capability URL is stored in ignored `private/connector-runtime.json`. After authentication, open the workspace from the UI. `login --open --browser ID` can reuse an existing terminal-browser window.

After a successful modeling step, publish a capture:

```sh
python3 fusion-workstation/workstation.py capture --step feature-001 --key capture-feature-001
```

The viewer polls the most recently published scene; it does not continually export the model from Fusion. Preserve designs before stopping a workstation. `workstation.py stop --target fresh` stops only the selected configured VM. `--all` includes configured workstations and the optional `FUSION_API_INSTANCE_ID` environment setting.

The optional `workstation.py run` adapter requires `FUSION_MODELING_ROOT` pointing to a separately installed modeling CLI with `tools/fusion-*` commands. Those external CLI tools are not bundled here.

## Offline checks

```sh
python3 fusion-workstation/test-workstation.py
python3 fusion-workstation/test-remote-auth.py
python3 fusion-workstation/test-connector.py
python3 fusion-workstation/test-transport.py
python3 fusion-workstation/test-viewer-parts.py
python3 fusion-workstation/test-auth-ui.py
python3 fusion-workstation/test-code-entry.py
```

These use mocks or local Chrome. They do not start EC2, submit real Autodesk credentials, or modify a live Fusion document. Keys, state files, authentication evidence, generated archives, and recordings remain ignored.

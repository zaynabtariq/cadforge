"""Offline lifecycle and routing regressions: never starts real instances."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import workstation as cli
from fusion_connector.vm import VM

class LifecycleTests(unittest.TestCase):
    def test_start_waits_for_stopping_and_checks_profile(self):
        vm=Mock();vm.state={'instance_id':'fresh-id','windows_user':'FusionAuth'}
        vm.describe.side_effect=[{'State':{'Name':s}} for s in ('stopping','stopped','pending','running')]
        vm.ssh.return_value='HOST\\FusionAuth'
        with patch.object(cli.time,'sleep'):cli.start(vm,10)
        vm.aws.assert_called_once_with('ec2','start-instances','--instance-ids','fresh-id')
        vm.resolve_address.assert_called_once()
    def test_wrong_identity_is_rejected(self):
        vm=Mock();vm.state={'windows_user':'FusionAuth'};vm.describe.return_value={'State':{'Name':'running'}};vm.ssh.return_value='HOST\\Fusion'
        with self.assertRaisesRegex(ValueError,'profile'):cli.start(vm,10)
    def test_stop_waits_for_confirmation(self):
        vm=Mock();vm.state={'instance_id':'fresh-id'}
        vm.describe.side_effect=[{'State':{'Name':s}} for s in ('running','stopping','stopped')]
        with patch.object(cli.time,'sleep'):cli.stop(vm,10)
        vm.aws.assert_called_once_with('ec2','stop-instances','--instance-ids','fresh-id')
    def test_run_does_not_start_stopped_vm(self):
        vm=Mock();vm.describe.return_value={'State':{'Name':'stopped'}}
        with patch.object(cli,'target',return_value=vm) as select,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['run','fusion-nav','state']),1)
        select.assert_called_once_with('fresh');vm.aws.assert_not_called();vm.connect.assert_not_called();vm.close.assert_called_once()
    def test_run_passes_owned_endpoint_and_exit_status(self):
        vm=Mock();bridge=Mock(endpoint='http://127.0.0.1:54321')
        with patch.object(cli,'target',return_value=vm),patch.object(cli,'verified_bridge',return_value=bridge),patch.object(cli.subprocess,'run',return_value=Mock(returncode=7)) as run:
            self.assertEqual(cli.main(['run','fusion-nav','state','--sparse']),7)
        self.assertEqual(run.call_args.kwargs['env']['FUSION_BRIDGE_URL'],bridge.endpoint)
        self.assertEqual(run.call_args.args[0][-3:],['fusion-nav','state','--sparse']);vm.close.assert_called_once()
    def test_stopped_auth_never_uses_cached_verification(self):
        vm=Mock();vm.describe.return_value={'InstanceId':'fresh-id','State':{'Name':'stopped'}}
        with patch.object(cli,'target',return_value=vm),patch.object(cli,'auth_status') as auth,contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['auth-status']),0)
        self.assertFalse(json.loads(out.getvalue())['verified']);auth.assert_not_called()
    def test_login_only_starts_fresh_and_no_secret_output(self):
        vm=Mock()
        with patch.object(cli,'target',return_value=vm) as select,patch.object(cli,'start') as start,patch.object(cli,'connector'),patch.object(cli,'api') as api,patch.object(cli,'auth_status',return_value={'phase':'credentials_required','verified':False}),contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['login']),0)
        select.assert_called_once_with('fresh');start.assert_called_once_with(vm,300);api.assert_called_once_with('v1/auth/start',{})
        self.assertNotIn('http',out.getvalue())
    def test_browser_ssh_resolves_new_ip_and_keeps_pinning_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'state.json';file.write_text(json.dumps({'instance_id':'test-instance','region':'us-west-2'}));vm=VM(file,Path(tmp)/'pinned-config')
            vm.describe=Mock(return_value={'State':{'Name':'running'},'PublicIpAddress':'203.0.113.22'})
            with patch('fusion_connector.vm.subprocess.Popen') as proc,patch('fusion_connector.vm.socket.create_connection'):
                proc.return_value.poll.return_value=None
                vm.connect_browser()
            command=proc.call_args.args[0]
            self.assertIn('HostName=203.0.113.22',command)
            self.assertIn(str(vm.ssh_config),command)
            self.assertNotIn('StrictHostKeyChecking=no',command)
    def test_runtime_rejects_nonlocal_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'private').mkdir()
            (root/'private/connector-runtime.json').write_text(json.dumps({'url':'https://example.com/secret/'}))
            with patch.object(cli,'ROOT',root),self.assertRaises(RuntimeError):cli.runtime_url()

if __name__=='__main__':unittest.main(verbosity=2)

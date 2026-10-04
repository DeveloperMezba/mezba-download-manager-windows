import io,json,os,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mdm import platform_support as platform,updater
from mdm.common import safe_name

class WindowsPort(unittest.TestCase):
    def test_reserved_windows_filenames(self):
        for name in ('CON','NUL.txt','COM1.mp4','lpt9'):
            self.assertTrue(safe_name(name).startswith('_'))
        self.assertEqual(safe_name('normal.mp4'),'normal.mp4')
    def test_locked_seek_write_for_windows_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'parts';fd=os.open(file,os.O_CREAT|os.O_RDWR|getattr(os,'O_BINARY',0),0o600);lock=threading.Lock()
            try:
                with patch.object(platform,'WINDOWS',True):
                    workers=[threading.Thread(target=platform.pwrite,args=(fd,bytes([i])*4096,i*4096,lock)) for i in range(12)]
                    for w in workers:w.start()
                    for w in workers:w.join()
                self.assertEqual(file.read_bytes(),b''.join(bytes([i])*4096 for i in range(12)))
            finally:os.close(fd)
    def test_update_repository_and_versions(self):
        self.assertEqual(updater.repository('https://github.com/mezba/mdm-windows'),'mezba/mdm-windows')
        self.assertGreater(updater.version('v0.10.0'),updater.version('0.9.0'))
        for text in ('https://evil.invalid/owner/repo','a/../b','a/repo?token=x'):
            with self.assertRaises(ValueError):updater.repository(text)
    def test_update_installer_checksum_and_repository(self):
        import hashlib
        data=b'MZ'+b'installer-fixture';digest=hashlib.sha256(data).hexdigest();name='Mezba-Download-Manager-0.1.3-Windows-x64-Setup.exe'
        base='https://github.com/me/mdm/releases/download/v0.1.3/'
        release={'tag_name':'v0.1.3','assets':[{'name':name,'size':len(data),'digest':'sha256:'+digest,'browser_download_url':base+name},{'name':'SHA256SUMS','browser_download_url':base+'SHA256SUMS'}]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(updater,'STATE',Path(tmp)),patch.object(updater,'init_state'):
            def metadata(url,limit):return json.dumps(release).encode() if url.endswith('/latest') else (digest+'  '+name+'\n').encode()
            with patch.object(updater,'read',side_effect=metadata),patch.object(updater,'open_url',return_value=io.BytesIO(data)):
                result=updater.check_and_download('me/mdm',lambda *_:None)
                self.assertEqual(Path(result['installer']).read_bytes(),data)
            release['assets'][0]['browser_download_url']='https://github.com/other/mdm/releases/download/v0.1.3/'+name
            with patch.object(updater,'read',side_effect=metadata),self.assertRaisesRegex(ValueError,'different repository'):
                updater.check_and_download('me/mdm',lambda *_:None)
    def test_legacy_release_number_does_not_reinstall_old_build(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(updater,'STATE',Path(tmp)),patch.object(updater,'init_state'):
            with patch.object(updater,'read',return_value=json.dumps({'tag_name':'v1.1.0'}).encode()):
                with self.assertRaisesRegex(ValueError,'legacy-numbered'):
                    updater.check_and_download('me/mdm',lambda *_:None)
    def test_service_rejects_wrong_token(self):
        import socket
        from mdm.ipc import Server,Handler
        with Server(('127.0.0.1',0),Handler) as server:
            server.token='secret';server.manager=type('Manager',(),{'dispatch':lambda self,msg:True})()
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                with socket.create_connection(server.server_address,timeout=3) as client:
                    client.sendall(json.dumps({'token':'wrong','message':{'action':'ping'}}).encode()+b'\n')
                    response=json.loads(client.makefile('rb').readline())
                self.assertFalse(response['ok']);self.assertEqual(response['error'],'Unauthorized')
            finally:server.shutdown();worker.join(timeout=3)

if __name__=='__main__':unittest.main()

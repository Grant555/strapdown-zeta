#!/usr/bin/env python2

import os
import sys
import unittest
import random
import string
import tempfile
import subprocess
import socket
import requests
import time
import shutil
import json

CWD = os.path.dirname(os.path.realpath(__file__))

def check_port(p):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    return sock.connect_ex(('127.0.0.1', p)) == 0


def random_name(length=10):
    return ''.join([random.choice(string.ascii_letters) for i in xrange(length)])

tmpfolders = []

class Test(unittest.TestCase):

    def writefile(self, fp, s):
        f = open(os.path.join(self.cwd, fp), 'w')
        f.write(s)
        f.close()

    def readfile(self, fp):
        f = open(os.path.join(self.cwd, fp), 'r')
        ret = f.read()
        f.close()
        return ret

    def url(self, urlpath):
        ret = "http://127.0.0.1:%d" % random.choice(self.ports)
        if not urlpath.startswith('/'):
            ret += '/'
        return ret + urlpath

    def setUp(self):
        self.cwd = tempfile.mkdtemp()
        tmpfolders.append(self.cwd)
        self.title = ''.join([random.choice(string.printable[:62]) for x in range(20)])
        self.ports = [random.randint(60000, 65535) for x in range(4)]
        self.writefile(".md", "# Wiki Index Page\n\nStrapdown Rocks!\n\n")
        BIN = "strapdown-server"
        self.binary = BIN
        if not os.path.exists("./" + BIN):
            print './%s not found' % BIN
            sys.exit(10)

        args = ["./" + BIN, "-verbose", "-dir=" + self.cwd, "-toc=true", "-title=" + self.title, "-init", "-heading_number=i", "-addr=" + ','.join(map(lambda x: '127.0.0.1:%d' % x, self.ports))]
        print args
        self.proc = subprocess.Popen(args, stdout=subprocess.PIPE)

        while True:
            for i in self.ports:
                if check_port(i):
                    print("test port true")
                    break
            else:
                continue
            break
        # wait other ports avaliable
        time.sleep(0.5)
        self.ports = filter(check_port, self.ports)
        self.assertGreater(len(self.ports), 0)

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait()

    def test_basic(self):
        text = u"This is a test"
        self.writefile(".md", text)
        r = requests.get(self.url('/'))
        self.assertIn(self.title, r.text, repr(r.text))
        self.assertIn(unicode(text), r.text, repr(r.text))
        self.assertGreater(len(r.text), len(text), repr(r.text))

        r = requests.get(self.url("/_static/version"))
        self.assertEqual(r.text, open(os.path.join(self.cwd, "_static", "version")).read())
        self.assertRegexpMatches(r.text, r'\d+\.\d+\.\d+(-\w+)?(\+[0-9A-Fa-f]{7,20})?')

        stdout = subprocess.check_output(['./' + self.binary, "-v"])
        self.assertRegexpMatches(stdout.strip(), r'\d+\.\d+\.\d+(-\w+)?(\+[0-9A-Fa-f]{7,20})?')

        hn = '.'.join([random.choice('ia') for _ in range(5)])
        r = requests.post(self.url("/.md.option.json"), data={
            "body": json.dumps({
                "HeadingNumber": hn
            })
        }, allow_redirects=False)
        self.assertIn(r.status_code, [301, 302, 303, 307, 308], r.status_code)

        r = requests.get(self.url("/"))
        self.assertIn(hn, r.text, repr(r.text))

        rc = random_name(50)
        r = requests.post(self.url("/version?edit"), data={
            "body": rc
        }, allow_redirects=False)

        r = requests.get(self.url("/version"))
        head = self.readfile(".git/refs/heads/master").strip()
        self.assertIn('version="%s"' % head, r.text, repr(r.text))
        self.assertIn(rc, r.text, repr(r.text))

        for i in range(10):
            requests.post(self.url("/version?edit"), data={
                "body": random_name(10)
            }, allow_redirects=False)

        r = requests.get(self.url("/version?version=%s" % head))
        self.assertIn(rc, r.text, repr(r.text))

    def test_raw_index(self):
        text = u"This is a test"
        self.writefile(".md", text)
        r = requests.get("http://127.0.0.1:%d/.md" % self.ports[0])
        self.assertEqual(text, r.text)

    def test_normal_post(self):
        text = u"This is a test"
        url = self.url("/test")
        r = requests.get(url)
        self.assertIn("edit.min.js", r.text)

        self.writefile("test.md", text)
        r = requests.get(url)
        self.assertIn("strapdown.min.js", r.text)
        self.assertIn(text, r.text)

        r = requests.get(url + "?edit")
        self.assertIn(text, r.text)
        self.assertIn("edit.min.js", r.text)

        r = requests.get(url + "?history")
        self.assertEqual(u'No commit history found for test.md\n', r.text)

        r = requests.get(url + "?diff")
        self.assertEqual(u'Bad params for diff, please select exactly TWO versions!\n', r.text)

        text = u"this is not a text"
        r = requests.post(url + "?edit", data={
            "body": text
        })
        self.assertIn(text, r.text)

    def test_dir_issue(self):
        folder1_name = random_name()
        folder1 = os.path.join(self.cwd, folder1_name)
        url = self.url("/")

        r = requests.get(url+folder1_name+"/")
        self.assertIn("edit.min.js", r.text, repr(r.text))

        os.makedirs(folder1)
        r = requests.get(url+folder1_name, allow_redirects=False)
        self.assertIn(r.status_code, [301, 302, 303, 307, 308], r.status_code)
        
        r = requests.get(url+folder1_name)
        self.assertIn('id="list"', r.text, repr(r.text))    # listdir

        text = 'This is some text'
        self.writefile(os.path.join(folder1, ".md"), text)
        r = requests.get(url+folder1_name)
        self.assertIn('strapdown.min.js', r.text)
        self.assertIn(text, r.text)

        folder2 = random_name() + ".md"
        os.makedirs(os.path.join(self.cwd, folder2))
        r = requests.get(url+folder2)
        self.assertIn('id="list"', r.text)

        r = requests.get(url+folder2[:-3])
        self.assertIn(r.status_code, [400, 404], r.status_code)
        self.assertIn(folder2, r.text, repr(r.text))
        self.assertIn("already exists and is a directory", r.text, repr(r.text))

    def test_upload(self):
        randomFile = os.urandom(20)
        filename = random_name() + '.mp4'
        r = requests.post(self.url(filename), files={
            "body": (filename, randomFile)
        })
        self.assertEqual(r.content, randomFile)
        self.assertEqual(open(os.path.join(self.cwd, filename), 'rb').read(), randomFile)
        self.assertEqual(r.headers['Content-Type'], "video/mp4")

    def test_upload_without_ext(self):
        randomFile = os.urandom(20)
        filename = random_name()
        r = requests.post(self.url(filename), files={
            "body": (filename, randomFile)
        })
        self.assertEqual(r.content, randomFile)
        self.assertEqual(open(os.path.join(self.cwd, filename), 'rb').read(), randomFile)
        self.assertEqual(r.headers['Content-Type'], "application/octet-stream")

    def test_content_type_for_static(self):
        self.writefile("www.css", "xxx")
        r = requests.get(self.url("/www.css"))
        self.assertEqual(r.headers['Content-Type'], "text/css; charset=utf-8")

    def test_uncommited_file(self):
        # make a history first
        r = requests.post(self.url("/?edit"), data={
            "body": "# awesome strapdown-server\n\n"
        })
        self.assertGreaterEqual(r.status_code, 200)
        self.assertLess(r.status_code, 300)

        r = requests.get(self.url("/?history"))
        self.assertRegexpMatches(r.text, r'<a href="\?version=[0-9a-f]{40}">')

        content = "var a = 1;\n"
        self.writefile("b.js", content)
        r = requests.get(self.url("/b.js"))
        self.assertEqual(r.text, content)

        r = requests.get(self.url("/.md?edit"))
        self.assertIn('?edit=raw', r.text)
        self.assertEqual(r.status_code, 400)

if __name__ == '__main__':
    os.chdir(CWD)
    suite = unittest.TestLoader().loadTestsFromTestCase(Test)

    # for command line tests
    # usage: ./test.py test_basic test_xxx test_xxx2
    tests = []

    if len(sys.argv) > 1:
        tests.extend(sys.argv[1:])

    if len(tests):
        suite = unittest.TestSuite(map(Test, tests))

    rs = unittest.TextTestRunner(verbosity=2).run(suite)
    try:
        for i in tmpfolders:
            shutil.rmtree(i)
    except:
        pass
    if len(rs.errors) > 0 or len(rs.failures) > 0:
        sys.exit(10)
    else:
        sys.exit(0)

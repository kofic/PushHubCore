import unittest
from mock import patch, Mock

from paste.util.multidict import MultiDict
from pyramid import testing
from pyramid.request import Request

from .views import publish, subscribe
from .models.hub import Hub
from .models.topic import Topic
from .models.subscriber import Subscriber
from .utils import is_valid_url

import os

path = os.path.abspath(os.path.dirname(__file__))

good_atom = open(path + '/fixtures/example.xml', 'r').read()


class MockResponse(object):
    def __init__(self, content=None, headers=None, status_code=None):
        self.content = content
        self.headers = headers
        self.status_code = status_code

    def __call__(self, *args, **kwargs):
        return self


class MultiResponse(object):
    def __init__(self, mapping):
        self.mapping = mapping

    def __call__(self, url, *args, **kwargs):
        if url in self.mapping.keys():
            return self.mapping[url]
        else:
            return MockResponse(status_code=404)


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()
        # Create an in-memory instance of the hub so requests can use it
        self.root = Hub()

    def tearDown(self):
        testing.tearDown()
        self.root = None

    def r(self, url, headers=[], POST={}):
        if not headers:
            headers = [("Content-Type", "application/x-www-form-urlencoded")]
        req = Request.blank(url,
                            headers=headers,
                            POST=POST)
        req.root = self.root
        return req


class PublishTests(BaseTest):

    valid_headers = [("Content-Type", "application/x-www-form-urlencoded")]

    def test_publish(self):
        request = Request.blank('/publish')
        info = publish(request)
        self.assertEqual(info.status_code, 405)

    def test_publish_wrong_type(self):
        """Post using an incorrect Content-Type"""
        headers = [('Content-Type', 'application/xml')]
        request = Request.blank('/publish',
                                headers=headers,
                                POST={'thing': 'thing'})
        info = publish(request)
        self.assertEqual(info.status_code, 406)

    def test_publish_content_type_without_mode(self):
        headers = [("Content-Type", "application/x-www-form-urlencoded")]
        request = self.r('/publish', headers, POST={})
        info = publish(request)
        self.assertEqual(info.status_code, 400)

    def test_publish_wrong_method(self):
        headers = [("Content-Type", "application/x-www-form-urlencoded")]
        request = Request.blank('', headers)
        info = publish(request)
        self.assertEqual(info.status_code, 405)
        self.assertEqual(info.headers['Allow'], 'POST')

    def test_publish_content_type_with_correct_mode(self):
        headers = [("Content-Type", "application/x-www-form-urlencoded")]
        data = {'hub.mode': 'publish', 'hub.url': 'http://www.google.com/'}
        request = self.r('/publish', headers, POST=data)
        info = publish(request)
        self.assertEqual(info.status_code, 204)

    def test_publish_content_type_with_incorrect_mode(self):
        headers = [("Content-Type", "application/x-www-form-urlencoded")]
        data = {'hub.mode': 'bad'}
        request = self.r('/publish', headers, POST=data)
        info = publish(request)
        self.assertEqual(info.status_code, 400)

    def test_publish_with_no_urls(self):
        data = {'hub.mode': 'publish'}
        request = self.r('/publish', self.valid_headers, POST=data)
        info = publish(request)
        self.assertEqual(info.status_code, 400)

    def test_publish_with_multiple_urls(self):
        data = MultiDict({'hub.mode': 'publish'})
        data.add('hub.url', 'http://www.example.com/')
        data.add('hub.url', 'http://www.site.com/')
        request = self.r('/publish', self.valid_headers, POST=data)
        info = publish(request)
        self.assertEqual(info.status_code, 204)


class SubscribeTests(BaseTest):
    default_data = MultiDict({
        'hub.verify': 'sync',
        # returns GET data so it will return the
        # hubs challenge string during verification
        'hub.callback': 'http://httpbin.org/get',
        'hub.mode': "subscribe",
        'hub.topic': "http://www.google.com/"
    })

    def test_subscribe(self):
        request = Request.blank('/subscribe')
        info = subscribe(request)
        self.assertEqual(info.status_code, 405)

    def test_invalid_content_type(self):
        headers = [("Content-Type", "text/plain")]
        request = self.r(
            '/subscribe',
            headers=headers,
            POST={"thing": "thing"}
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 406)
        self.assertEqual(
            info.headers['Accept'],
            'application/x-www-form-urlencoded'
        )

    def test_invalid_verify_type(self):
        data = {"hub.verify": "bogus"}
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 400)
        self.assertEqual(info.headers['Content-Type'], 'text/plain')
        self.assertTrue("hub.verify" in info.body)

    def test_multiple_verify_types_one_valid(self):
        data = self.default_data.copy()
        del data["hub.verify"]
        data.add('hub.verify', 'bogus')
        data.add('hub.verify', 'sync')
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 204)

    def test_multiple_invalid_verify_types(self):
        data = self.default_data.copy()
        del data["hub.verify"]
        data.add('hub.verify', 'bad')
        data.add('hub.verify', 'wrong')
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 400)
        self.assertEqual(info.headers['Content-Type'], 'text/plain')
        self.assertTrue("hub.verify" in info.body)

    def test_invalid_callback(self):
        data = self.default_data.copy()
        del data['hub.callback']
        data.add("hub.callback", "www.google.com")
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 400)
        self.assertTrue('hub.callback' in info.body)

    def test_valid_callback(self):
        data = self.default_data.copy()
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 204)

    def test_invalid_mode(self):
        data = self.default_data.copy()
        del data['hub.mode']
        data.add('hub.mode', 'bad')
        request = self.r(
            '/subscribe',
            POST=data,
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 400)
        self.assertTrue('hub.mode' in info.body)

    def test_valid_mode(self):
        data = self.default_data.copy()
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 204)

    def test_valid_topic(self):
        data = self.default_data.copy()
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 204)

    def test_invalid_topic(self):
        data = self.default_data.copy()
        del data['hub.topic']
        data.add('hub.topic', 'http://google.com/#fragment')
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 400)
        self.assertTrue('hub.topic' in info.body)

    def test_not_verified_subscription(self):
        data = self.default_data.copy()
        del data["hub.callback"]
        data.add('hub.callback', 'http://httpbin.org/status/404')
        request = self.r(
            '/subscribe',
            POST=data
        )
        info = subscribe(request)
        self.assertEqual(info.status_code, 409)


class SubscriberTests(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_creation(self):
        s = Subscriber('http://www.google.com')
        self.assertEqual(s.callback_url, 'http://www.google.com')

    def test_bad_urls(self):
        """
        A 'good' URL will have:
            * a scheme
            * a netloc (usually server, domain, and TLD names)
            * not only a path
            * no fragments
            # a valid port
        """
        self.assertRaises(ValueError, Subscriber, 'http://')
        self.assertRaises(ValueError, Subscriber, 'www.site.com')
        self.assertRaises(ValueError, Subscriber, '/path-only')
        self.assertRaises(
            ValueError,
            Subscriber,
            'http://google.com/#fragment'
        )


class TopicTests(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_creation(self):
        t = Topic('http://www.google.com/')
        self.assertEqual(t.url, 'http://www.google.com/')
        self.assertEqual(t.timestamp, None)
        self.assertEqual(t.content, None)

    def test_bad_urls(self):
        """
        A 'good' URL will have:
            * a scheme
            * a netloc (usually server, domain, and TLD names)
            * a path
        """
        self.assertRaises(ValueError, Topic, 'http://')
        self.assertRaises(ValueError, Topic, 'www.site.com')
        self.assertRaises(ValueError, Topic, '/path-only')

    def test_pinged_time(self):
        t = Topic('http://www.google.com/')
        original_time = t.last_pinged
        t.ping()
        new_time = t.last_pinged
        self.assertTrue(original_time < new_time)

    def test_adding_subscriber(self):
        t = Topic('http://www.google.com/')
        t.add_subscriber()
        self.assertEqual(t.subscribers, 1)

    def test_removing_subscriber(self):
        t = Topic('http://www.google.com/')
        t.add_subscriber()
        t.remove_subscriber()
        self.assertEqual(t.subscribers, 0)

    def test_removing_too_many_subscribers(self):
        t = Topic('http://www.google.com/')
        self.assertRaises(ValueError, t.remove_subscriber)

    def test_fetching_bad_content(self):
        t = Topic('http://httpbin.org/get')
        self.assertRaises(ValueError, t.fetch, 'http://myhub.com/')
        # Nothing should be changed if the fetch fails
        self.assertTrue(t.timestamp is None)
        self.assertTrue(t.content is None)

    @patch('requests.get', new_callable=MockResponse, content=good_atom)
    def test_fetching_good_content(self, mock):
        t = Topic('http://httpbin.org/get')
        t.fetch('http://myhub.com/')
        self.assertTrue('John Doe' in t.content)
        self.assertTrue(t.timestamp is not None)

    def test_verify_bad_content(self):
        t = Topic('http://httpbin.org/get')
        bad_content = 'this is bad'
        self.assertFalse(t.verify(bad_content))

    def test_verify_good_content(self):
        t = Topic('http://httpbin.org/get')
        self.assertTrue(t.verify(good_atom))


class HubTests(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_creation(self):
        hub = Hub()
        self.assertEqual(hub.topics, None)
        self.assertEqual(hub.subscribers, None)

    def test_publish_topic(self):
        hub = Hub()
        hub.publish('http://www.google.com/')
        self.assertEqual(len(hub.topics), 1)
        self.assertTrue('http://www.google.com/' in hub.topics.keys())
        self.assertEqual(
            hub.topics['http://www.google.com/'].url,
            'http://www.google.com/'
        )

    def test_publish_existing_topic(self):
        """
        Existing topics should have their 'pinged' time updated.
        """
        hub = Hub()
        hub.publish('http://www.google.com/')
        first_time = hub.topics['http://www.google.com/'].last_pinged
        hub.publish('http://www.google.com/')
        second_time = hub.topics['http://www.google.com/'].last_pinged
        self.assertEqual(len(hub.topics), 1)
        self.assertTrue(second_time > first_time)

    def test_subscribe(self):
        hub = Hub()
        hub.subscribe('http://www.google.com/', 'http://www.google.com/')
        self.assertEqual(len(hub.subscribers), 1)
        self.assertTrue('http://www.google.com/' in hub.subscribers.keys())
        self.assertEqual(
            hub.subscribers['http://www.google.com/'].callback_url,
            'http://www.google.com/'
        )

    def test_existing_subscription(self):
        hub = Hub()
        hub.subscribe('http://www.google.com/', 'http://www.google.com/')
        hub.subscribe('http://www.google.com/', 'http://www.google.com/')
        self.assertEqual(len(hub.subscribers), 1)
        sub = hub.get_or_create_subscriber('http://www.google.com/')
        self.assertEqual(len(sub.topics), 1)

    def test_unsubscribe(self):
        hub = Hub()
        hub.subscribe('http://www.google.com/', 'http://www.google.com/')
        sub = hub.get_or_create_subscriber('http://www.google.com/')
        self.assertEqual(len(sub.topics), 1)
        self.assertTrue('http://www.google.com/' in sub.topics.keys())
        hub.unsubscribe('http://www.google.com/', 'http://www.google.com/')
        self.assertEqual(len(sub.topics), 0)
        # test repeated unsubscribe
        hub.unsubscribe('http://www.google.com/', 'http://www.google.com/')
        self.assertEqual(len(sub.topics), 0)

    @patch('requests.get', new_callable=MockResponse, content=good_atom)
    def test_fetch_all_topics(self, mock):
        hub = Hub()
        hub.publish('http://httpbin.org/get')
        hub.publish('http://www.google.com/')
        hub.fetch_content('http://myhub.com')
        first = hub.topics.get('http://httpbin.org/get')
        second = hub.topics.get('http://www.google.com/')
        self.assertTrue(first.timestamp is not None)
        self.assertTrue('John Doe' in first.content)
        self.assertTrue(second.timestamp is not None)
        self.assertTrue('John Doe' in second.content)

    def test_fetch_all_topics_one_error(self):
        """Allow a test topic to fail; others should be unaffected
        """
        hub = Hub()
        hub.publish('http://httpbin.org/get')
        hub.publish('http://www.google.com/')
        urls = {
            'http://httpbin.org/get': MockResponse(content=good_atom),
            'http://www.google.com/': MockResponse(content="adslkfhadslfhd"),
        }
        with patch('requests.get', new_callable=MultiResponse, mapping=urls):
            hub.fetch_content('http://myhub.com')
        good = hub.topics.get('http://httpbin.org/get')
        bad = hub.topics.get('http://www.google.com/')

        self.assertTrue(good.timestamp is not None)
        self.assertTrue('John Doe' in good.content)

        self.assertTrue(bad.timestamp is None)
        self.assertTrue(bad.content is None)


class UtilTests(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_is_valid_url(self):
        """
        A 'good' URL will have:
            * a scheme
            * a netloc (usually server, domain, and TLD names)
            * not only a path
            * no fragments
            # a valid port
        """
        self.assertFalse(is_valid_url('google.com'))
        self.assertFalse(is_valid_url('http://google.com/#fragment'))
        # see .views.VALID_PORTS for a list of valid ports
        self.assertFalse(is_valid_url('https://www.google.com:8888'))
        self.assertFalse(is_valid_url("/path"))
        self.assertFalse(is_valid_url("http://"))

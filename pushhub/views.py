from pyramid.httpexceptions import exception_response

from .utils import require_post, is_valid_url, normalize_iri

import logging
logger = logging.getLogger(__name__)

# Default expiration time of a lease.
DEFAULT_LEASE_SECONDS = (5 * 24 * 60 * 60)  # 5 days


@require_post
def publish(context, request):
    topic_mode = request.POST.get('hub.mode', '')
    topic_urls = request.POST.getall('hub.url')

    bad_data = False
    error_msg = None

    if not topic_mode or topic_mode != 'publish':
        bad_data = True
        error_msg = "Invalid or unspecified mode."

    if not topic_urls:
        bad_data = True
        error_msg = "No topic URLs provided"

    hub = request.root

    for topic_url in topic_urls:
        try:
            hub.publish(topic_url)
        except ValueError:
            bad_data = True
            error_msg = "Malformed URL: %s" % topic_url

    if not bad_data:
        hub.fetch_all_content(request.application_url)

    if bad_data and error_msg:
        return exception_response(400,
                                  body=error_msg,
                                  headers=[('Content-Type', 'text/plain')])

    hub.notify_subscribers()

    topics = [t for (k, t) in hub.topics.items() if k in topic_urls]
    hub.notify_listeners(topics)

    return exception_response(204)


@require_post
def subscribe(context, request):
    # required
    callback = request.POST.get('hub.callback', '')
    topic = request.POST.get('hub.topic', '')
    verify_type_list = [s.lower() for s in request.POST.getall('hub.verify')]
    mode = request.POST.get('hub.mode', '').lower()
    # optional, per the spec we can support these or not.
    # TODO: support for the following optional arguments
    verify_token = unicode(request.POST.get('hub.verify_token', ''))
    secret = unicode(request.POST.get('hub.secret', '')) or None
    verify_callbacks = request.POST.get('hub.verify_callbacks', 'True')
    verify_callbacks = verify_callbacks == 'True'

    lease_seconds = (
        request.POST.get('hub.lease_seconds', '') or
        str(DEFAULT_LEASE_SECONDS)
    )

    error_message = None
    if not callback or not is_valid_url(callback):
        error_message = (
            'Invalid parameter: hub.callback; '
            'must be valid URI with no fragment and '
            'optional port'
        )
    else:
        callback = normalize_iri(callback)

    if not topic or not is_valid_url(topic):
        error_message = (
            'Invalid parameter: hub.topic; '
            'must be valid URI with no fragment and '
            'optional port'
        )
    else:
        topic = normalize_iri(topic)

    if mode not in ('subscribe', 'unsubscribe'):
        error_message = (
            'Invalid parameter: hub.mode; '
            'Supported values are "subscribe", "unsubscribe"'
            'Given: %s' % mode
        )

    enabled_types = [
        vtype for vtype in verify_type_list
        if vtype in ('async', 'sync')
    ]

    if not enabled_types:
        error_message = (
            'Invalid values for hub.verify: %s' %
            (verify_type_list,)
        )
    else:
        verify_type = enabled_types

    if error_message:
        return exception_response(
            400,
            body=error_message,
            headers=[("Content-Type", "text/plain")]
        )

    hub = request.root

    # give preference to sync
    if 'sync' in verify_type:
        if mode == 'subscribe':
            verified = hub.subscribe(callback, topic, verify_callbacks=verify_callbacks)
        else:
            verified = hub.unsubscribe(callback, topic, verify_callbacks=verify_callbacks)

        if not verified:
            return exception_response(
                409,
                body="Subscription intent not verified",
                headers=[("Content-Type", "text/plain")]
            )
            logger.info('Could not verify intent for subscriber %s', callback)
    else:
        # TODO: async verification
        # should return a 202 and then perform verification
        # at a later date as determined by the hub
        # we'll return a 400 right now until it's supported
        return exception_response(
            400,
            body="async verification currently not supported",
            headers=[("Content-Type", "text/plain")]
        )
        logger.info('Request for async verification by %s', callback)
    # verified and active
    return exception_response(204)


@require_post
def listen(context, request):
    listener_url = request.POST.get('listener.callback', '')
    error_msg = ''

    if not listener_url:
        error_msg = "Malformed URL: %s" % listener_url

    hub = request.root

    try:
        hub.register_listener(listener_url)
    except ValueError as e:
        error_msg = str(e)

    if error_msg:
        return exception_response(400,
                                  body=error_msg,
                                  headers=[('Content-Type', 'text/plain')])
    return exception_response(200)



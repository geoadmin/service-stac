# Static Assets

> `Status: accepted`

> `Date: 2020-10-21`

> `Participants: Brice Schaffner, Christoph Böcklin`

## Context

`service-stac` needs to serve some static assets for the admin pages (css, images, icons, ...). Django is not appropriate to serve static files on production environment. Currently Django is served directly by `gunicorn`. As a good practice to avoid issue with slow client and to avoid Denial of Service attacks, `gunicorn` should be served behind a Reversed proxy (e.g. Apache or Nginx).

## Decision

Because it is to us not clear yet if a Reverse Proxy is really necessary for our Architecture (CloudFront with Kubernetes Ingress), we decided to use WhiteNoise for static assets. This middleware seems to performs well with CDN (like CloudFront) therefore we will use it to serve static files as it is very simple to uses and take care of compressing and settings corrects Headers for caching.

## Consequences

We might have to reconsider in future using a Reverse Proxy for `gunicorn` and then uses this proxy (e.g. nginx) to serve static files instead of Whitenoise.

## References

- [Static Files Made Easy — Django Compressor + Whitenoise + AWS CloudFront + Heroku](https://medium.com/technolingo/fastest-static-files-served-django-compressor-whitenoise-aws-cloudfront-ef777849090c)
- [Isn’t serving static files from Python horribly inefficient?](https://whitenoise.readthedocs.io/en/stable/index.html#isn-t-serving-static-files-from-python-horribly-inefficient)

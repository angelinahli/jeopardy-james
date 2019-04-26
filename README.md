# High-level approach

Pretty straight-forawrd implementation. I have some helper methods to handle
HTTP requests. After handling the log-in, I collect all the links, add them to a
queue, and process any same-domain links which haven't been processed yet.

For performance, I set up the requests to be done on up to 10 threads at once.
The actual processing of each HTML page is done synchonously, to avoid race
conditions with any counters

# Challenges

I found it unintuitive to figure out when I could use "\r\n" vs. "\n\n" in
python (I still don't really get it). Pipelining was too hard to implement, and
gzipping got complicated when the response was chunked, so the only performance
improvement I added was threading. Handling chunks at all was definitely the
hardest part of the assignment.

# Testing

I mostly just let the scraper run and logged anything that might be useful for
debugging.

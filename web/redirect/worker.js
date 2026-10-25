export default {
  fetch(request) {
    const source = new URL(request.url);
    const target = new URL('https://halite3.cmander02.com');
    target.pathname = source.pathname.replace(/^\/halite3(?:\/|$)/, '/') || '/';
    target.search = source.search;
    return Response.redirect(target.toString(), 308);
  }
};

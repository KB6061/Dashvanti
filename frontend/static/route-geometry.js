(() => {
  const point = value => ({lat: typeof value.lat === 'function' ? value.lat() : Number(value.lat), lng: typeof value.lng === 'function' ? value.lng() : Number(value.lng)});
  const distance = (a, b) => {
    const radians = Math.PI / 180, latitude = (a.lat + b.lat) * radians / 2;
    return Math.hypot((b.lat - a.lat) * 111320, (b.lng - a.lng) * 111320 * Math.cos(latitude));
  };
  const bearing = (a, b) => (Math.atan2((b.lng - a.lng) * Math.cos((a.lat + b.lat) * Math.PI / 360), b.lat - a.lat) * 180 / Math.PI + 360) % 360;
  const angleDifference = (a, b) => Math.abs((a - b + 540) % 360 - 180);
  const build = route => {
    const path = [], steps = [];
    let travelled = 0;
    for (const leg of route.legs || []) {
      for (const step of leg.steps || []) {
        const start = travelled;
        for (const value of step.path || [step.start_location, step.end_location]) {
          if (!value) continue;
          const next = point(value), previous = path.at(-1);
          const length = previous ? distance(previous, next) : 0;
          if (previous && length < 0.05) continue;
          travelled += length;
          path.push({...next, metres: travelled});
        }
        steps.push({...step, from: start, to: travelled});
      }
    }
    if (path.length < 2) {
      for (const value of route.overview_path || []) {
        const next = point(value);
        travelled += path.length ? distance(path.at(-1), next) : 0;
        path.push({...next, metres: travelled});
      }
    }
    return {path, steps};
  };
  const project = (path, location, previousMetres = null) => {
    const raw = {lat: location.latitude, lng: location.longitude};
    const scale = 111320, cosine = Math.cos(raw.lat * Math.PI / 180);
    const moving = Number.isFinite(location.heading) && location.speed > 2;
    let best = null, nearest = Infinity;
    for (let index = 1; index < path.length; index++) {
      const a = path[index - 1], b = path[index];
      const ax = (a.lat - raw.lat) * scale, ay = (a.lng - raw.lng) * scale * cosine;
      const dx = (b.lat - a.lat) * scale, dy = (b.lng - a.lng) * scale * cosine;
      const length = dx * dx + dy * dy;
      if (!length) continue;
      const fraction = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / length));
      const gap = Math.hypot(ax + fraction * dx, ay + fraction * dy);
      nearest = Math.min(nearest, gap);
      const heading = bearing(a, b), metres = a.metres + fraction * (b.metres - a.metres);
      const wrongHeading = moving && angleDifference(location.heading, heading) > 100;
      const backwards = previousMetres !== null && metres < previousMetres - 35;
      const score = gap + (wrongHeading ? 35 : 0) + (backwards ? 15 : 0);
      if (!best || score < best.score) best = {point: {lat: a.lat + fraction * (b.lat - a.lat), lng: a.lng + fraction * (b.lng - a.lng)}, heading, metres, gap, score, wrongHeading};
    }
    const accuracy = Number.isFinite(location.accuracy) ? location.accuracy : 15;
    const reliable = accuracy <= 60;
    const snapped = best && reliable && best.gap <= Math.min(30, Math.max(15, accuracy)) && !best.wrongHeading;
    return {
      point: snapped ? best.point : raw,
      heading: snapped ? best.heading : Number.isFinite(location.heading) ? location.heading : best?.heading,
      metres: best?.metres, snapped: Boolean(snapped), gap: nearest,
      offRoute: Boolean(best && reliable && (nearest > Math.max(35, accuracy * 1.5) || (nearest < 25 && best.wrongHeading)))
    };
  };
  const journey = (path, previous, next) => {
    if (!previous?.snapped || !next.snapped || next.metres < previous.metres || next.metres - previous.metres > 250) return [previous?.point, next.point].filter(Boolean);
    return [previous.point, ...path.filter(value => value.metres > previous.metres && value.metres < next.metres), next.point];
  };
  const interpolate = (path, fraction) => {
    const lengths = path.slice(1).map((value, index) => distance(path[index], value));
    let remaining = lengths.reduce((sum, value) => sum + value, 0) * fraction;
    for (let index = 0; index < lengths.length; index++) {
      if (remaining <= lengths[index] || index === lengths.length - 1) {
        const ratio = lengths[index] ? remaining / lengths[index] : 1, a = path[index], b = path[index + 1];
        return {lat: a.lat + (b.lat - a.lat) * ratio, lng: a.lng + (b.lng - a.lng) * ratio, heading: bearing(a, b)};
      }
      remaining -= lengths[index];
    }
    return path.at(-1);
  };
  const geometry = {point, distance, bearing, angleDifference, build, project, journey, interpolate};
  if (typeof module !== 'undefined') module.exports = geometry;
  else window.dashvantiRouteGeometry = geometry;
})();

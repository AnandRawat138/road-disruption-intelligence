import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl, { GeoJSONSource, LngLatBoundsLike, Map as MLMap } from 'maplibre-gl'
import { ExternalLink, Maximize2, RotateCcw, X } from 'lucide-react'
import { fmtDate, qs, useApi } from '../api'
import { usePublicSettings } from '../App'
import { CATEGORY_META, INCIDENT_STATUSES, SEVERITIES, SEVERITY_GLYPH_INK, SEVERITY_META, SEVERITY_RAMP } from '../meta'
import { Badge, CategoryBadge, ErrorBox, Loading, MultiSelect, Notice, PrecisionBadge, Severity, StatusBadge } from '../components/ui'
import IncidentDrawer from '../components/IncidentDrawer'
import { LIFECYCLES, useIncidentFilters } from './Disruptions'

const sevExpr: any = ['match', ['get', 'severity'], ...Object.entries(SEVERITY_RAMP).flat(), SEVERITY_RAMP.UNKNOWN]
const inkExpr: any = ['match', ['get', 'severity'], ...Object.entries(SEVERITY_GLYPH_INK).flat(), '#101828']
const glyphExpr: any = ['match', ['get', 'category'], ...Object.entries(CATEGORY_META).flatMap(([k, v]) => [k, v.glyph]), '?']

function daysAgo(n: number) {
  const d = new Date(Date.now() - n * 86400000)
  return d.toISOString().slice(0, 10)
}

export default function MapPage() {
  const { s } = usePublicSettings()
  const { f, update } = useIncidentFilters()
  const [includeState, setIncludeState] = useState(false)
  const geoPath = `/api/map/incidents${qs({ ...f, include_state_level: includeState ? 'true' : '' })}`
  const geo = useApi<any>(geoPath)
  const list = useApi<any>(`/api/incidents${qs({ ...f, page_size: 100, sort: 'last_reported_at' })}`)
  const mapRef = useRef<MLMap | null>(null)
  const el = useRef<HTMLDivElement>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [drawer, setDrawer] = useState<string | null>(null)
  const detail = useApi<any>(selected ? `/api/incidents/${selected}` : null)
  const [region, setRegion] = useState('')

  // ---------------------------------------------------------------- init map once
  useEffect(() => {
    if (!el.current) return
    let map: MLMap
    try {
      map = new maplibregl.Map({
        container: el.current, style: s.map.style_url,
        center: [s.map.default_center[1], s.map.default_center[0]], zoom: s.map.default_zoom, attributionControl: false,
      })
    } catch (e: any) {
      setMapError(`The map could not start (${e?.message || 'WebGL unavailable'}). The incident list still works.`)
      return
    }
    mapRef.current = map
    const ro = new ResizeObserver(() => map.resize())
    ro.observe(el.current)
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: s.map.attribution_note }), 'bottom-right')
    let styleLoaded = false
    const timer = window.setTimeout(() => {
      if (!styleLoaded) setMapError('Map tiles could not be loaded. An internet connection is required for the basemap; incident data is still listed on the left.')
    }, 15000)
    map.on('error', (ev: any) => {
      if (!styleLoaded) setMapError('Map tiles could not be loaded. An internet connection is required for the basemap; incident data is still listed on the left.')
      else console.warn('Map error', ev?.error?.message)
    })
    map.on('load', () => {
      styleLoaded = true
      window.clearTimeout(timer)
      setMapError(null)
      map.addSource('incidents', { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, cluster: true, clusterRadius: 42, clusterMaxZoom: 11 })
      map.addLayer({ id: 'clusters', type: 'circle', source: 'incidents', filter: ['has', 'point_count'],
        paint: { 'circle-color': '#13315c', 'circle-opacity': 0.88, 'circle-stroke-color': '#fff', 'circle-stroke-width': 2,
                 'circle-radius': ['step', ['get', 'point_count'], 15, 10, 19, 50, 24, 200, 30] } })
      map.addLayer({ id: 'cluster-count', type: 'symbol', source: 'incidents', filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['Noto Sans Regular'] },
        paint: { 'text-color': '#fff' } })
      // Approximate-location ring: city/locality centroids are drawn with a translucent halo.
      map.addLayer({ id: 'approx-ring', type: 'circle', source: 'incidents', filter: ['all', ['!', ['has', 'point_count']], ['in', ['get', 'geo_precision'], ['literal', ['CITY', 'STATE']]]],
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 14, 10, 40], 'circle-color': sevExpr, 'circle-opacity': 0.12,
                 'circle-stroke-color': sevExpr, 'circle-stroke-width': 1, 'circle-stroke-opacity': 0.4 } })
      map.addLayer({ id: 'points', type: 'circle', source: 'incidents', filter: ['!', ['has', 'point_count']],
        paint: { 'circle-radius': ['match', ['get', 'severity'], 'CRITICAL', 13, 'HIGH', 12, 'MODERATE', 11, 10],
                 'circle-color': sevExpr, 'circle-stroke-color': ['case', ['==', ['get', 'status'], 'CONFIRMED'], '#101828', '#ffffff'],
                 'circle-stroke-width': ['case', ['==', ['get', 'status'], 'CONFIRMED'], 2.5, 1.8],
                 'circle-opacity': ['case', ['get', 'is_stale'], 0.6, 1] } })
      map.addLayer({ id: 'point-glyph', type: 'symbol', source: 'incidents', filter: ['!', ['has', 'point_count']],
        layout: { 'text-field': glyphExpr, 'text-size': 9, 'text-font': ['Noto Sans Regular'], 'text-allow-overlap': true },
        paint: { 'text-color': inkExpr } })
      map.addLayer({ id: 'selected', type: 'circle', source: 'incidents', filter: ['==', ['get', 'id'], ''],
        paint: { 'circle-radius': 17, 'circle-color': 'transparent', 'circle-stroke-color': '#1d4ed8', 'circle-stroke-width': 3 } })

      map.on('click', 'clusters', e => {
        const feat = e.features?.[0]
        if (!feat) return
        const src = map.getSource('incidents') as GeoJSONSource
        src.getClusterExpansionZoom((feat.properties as any).cluster_id, (err: any, zoom: number | null | undefined) => {
          if (!err && zoom != null) map.easeTo({ center: (feat.geometry as any).coordinates, zoom })
        })
      })
      map.on('click', 'points', e => { const id = e.features?.[0]?.properties?.id; if (id) setSelected(String(id)) })
      for (const layer of ['clusters', 'points']) {
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      setReady(true)
    })
    return () => { ro.disconnect(); window.clearTimeout(timer); map.remove(); mapRef.current = null; setReady(false) }
  }, [s.map.style_url])

  // ---------------------------------------------------------------- data → map
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !geo.data) return
    ;(map.getSource('incidents') as GeoJSONSource | undefined)?.setData(geo.data)
  }, [geo.data, ready])

  useEffect(() => {
    const map = mapRef.current
    if (ready && map?.getLayer('selected')) map.setFilter('selected', ['==', ['get', 'id'], selected || ''])
  }, [selected, ready])

  const bounds = useMemo<LngLatBoundsLike | null>(() => {
    const feats = geo.data?.features || []
    if (!feats.length) return null
    const b = new maplibregl.LngLatBounds()
    feats.forEach((ft: any) => b.extend(ft.geometry.coordinates))
    return b
  }, [geo.data])
  const fit = () => { if (bounds && mapRef.current) mapRef.current.fitBounds(bounds, { padding: 60, maxZoom: 11, duration: 600 }) }
  const reset = () => { setRegion(''); mapRef.current?.flyTo({ center: [s.map.default_center[1], s.map.default_center[0]], zoom: s.map.default_zoom }) }
  const focus = (name: string) => {
    setRegion(name)
    const r = s.map.focus_regions[name]
    if (r) mapRef.current?.flyTo({ center: [r[1], r[0]], zoom: r[2] })
  }
  const selectFromList = (id: string) => {
    setSelected(id)
    const ft = geo.data?.features?.find((x: any) => x.properties.id === id)
    if (ft && mapRef.current) mapRef.current.flyTo({ center: ft.geometry.coordinates, zoom: Math.max(mapRef.current.getZoom(), 9) })
  }
  const meta = geo.data?.meta
  const mapped = new Set((geo.data?.features || []).map((x: any) => x.properties.id))
  const quick = (n: number | null) => update({ date_from: n ? daysAgo(n) : '', date_to: '' })
  const inc = detail.data?.incident
  return (
    <div className="map-layout">
      <aside className="map-side" aria-label="Map filters and incident list">
        <details className="map-filters" open={window.innerWidth > 820}>
        <summary className="small" style={{ padding: '8px 14px', cursor: 'pointer', fontWeight: 600 }}>Filters{Object.keys(f).length ? ` (${Object.keys(f).length} active)` : ''}</summary>
        <div className="filters">
          <div className="row" role="radiogroup" aria-label="Lifecycle">
            {LIFECYCLES.map(l => <button key={l.id} className={`btn sm ${(f.lifecycle || '') === l.id ? 'primary' : ''}`} role="radio" aria-checked={(f.lifecycle || '') === l.id} onClick={() => update({ lifecycle: l.id })}>{l.label}</button>)}
          </div>
          <div className="row">
            <MultiSelect label="Category" options={s.categories.map(c => ({ value: c.code, label: c.label }))} value={f.category || []} onChange={v => update({ category: v })} />
            <MultiSelect label="Severity" options={SEVERITIES.map(x => ({ value: x, label: SEVERITY_META[x].label }))} value={f.severity || []} onChange={v => update({ severity: v })} />
            <MultiSelect label="Status" options={INCIDENT_STATUSES.map(x => ({ value: x, label: x }))} value={f.status || []} onChange={v => update({ status: v })} />
          </div>
          <div className="row">
            <input className="input" placeholder="City" value={f.city || ''} onChange={e => update({ city: e.target.value })} style={{ width: 100 }} aria-label="City" />
            <input className="input" placeholder="State" value={f.state || ''} onChange={e => update({ state: e.target.value })} style={{ width: 100 }} aria-label="State" />
            <input className="input" placeholder="NH-48" value={f.highway || ''} onChange={e => update({ highway: e.target.value })} style={{ width: 80 }} aria-label="Highway" />
          </div>
          <div className="row">
            <input className="input" placeholder="Source name" value={f.source || ''} onChange={e => update({ source: e.target.value })} style={{ flex: 1 }} aria-label="Source" />
            <select className="input" value={f.classification || ''} onChange={e => update({ classification: e.target.value })} aria-label="Review state">
              <option value="">Any review state</option><option value="approved">Has approved report</option><option value="pending">Has pending report</option>
            </select>
          </div>
          <div className="row small">
            <span className="muted">Time:</span>
            {[[7, '7 d'], [30, '30 d'], [90, '90 d'], [null, 'All']].map(([n, l]) => <button key={String(l)} className="btn sm" onClick={() => quick(n as number | null)}>{l}</button>)}
          </div>
          <div className="row">
            <input type="date" className="input" value={f.date_from || ''} onChange={e => update({ date_from: e.target.value })} aria-label="Reported from" />
            <input type="date" className="input" value={f.date_to || ''} onChange={e => update({ date_to: e.target.value })} aria-label="Reported to" />
          </div>
          <label className="check small"><input type="checkbox" checked={includeState} onChange={e => setIncludeState(e.target.checked)} />Include state-level (very approximate) locations</label>
        </div>
        </details>
        <div className="small muted" style={{ padding: '8px 14px', borderBottom: '1px solid var(--border)' }}>
          {meta ? <>{meta.mapped} on map · <strong>{meta.unmapped}</strong> without a usable location{list.data && list.data.total > 100 ? ' · list shows latest 100' : ''}</> : 'Loading…'}
        </div>
        <div className="map-list">
          {list.error && <div style={{ padding: 12 }}><ErrorBox error={list.error} onRetry={list.reload} /></div>}
          {list.loading && !list.data && <Loading />}
          {list.data?.items.length === 0 && <div className="empty small">No incidents match. Incidents appear after relevant records are classified.</div>}
          {list.data?.items.map((i: any) => (
            <button key={i.id} className={`map-item ${selected === i.id ? 'active' : ''}`} onClick={() => selectFromList(i.id)}>
              <div className="row" style={{ gap: 6 }}><CategoryBadge code={i.category} /><Severity value={i.severity} />{!mapped.has(i.id) && <Badge title="No usable location">not mapped</Badge>}</div>
              <div style={{ fontWeight: 500, marginTop: 4 }}>{i.title}</div>
              <div className="xs muted">{[i.city, i.state].filter(Boolean).join(', ') || 'location unknown'} · {fmtDate(i.last_reported_at)} · {i.status.toLowerCase()}{i.is_stale ? ' (stale)' : ''}</div>
            </button>
          ))}
        </div>
      </aside>

      <div className="map-wrap">
        <div ref={el} className="map-canvas" role="application" aria-label="Map of incidents" />
        {mapError && <div className="map-error"><Notice kind="warn">{mapError}</Notice></div>}
        <div className="map-toolbar">
          <button className="btn sm" onClick={fit} disabled={!bounds}><Maximize2 size={13} />Fit to results</button>
          <button className="btn sm" onClick={reset}><RotateCcw size={13} />Reset view</button>
          <select className="input" value={region} onChange={e => focus(e.target.value)} aria-label="Focus region">
            <option value="">Focus region…</option>{Object.keys(s.map.focus_regions).map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          {geo.loading && <span className="btn sm" aria-live="polite"><span className="spinner" style={{ width: 12, height: 12 }} />Updating</span>}
        </div>
        <details className="legend" open={window.innerWidth > 1200}>
          <summary style={{ fontWeight: 600, cursor: 'pointer' }}>Legend · severity (fill)</summary>
          {['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'UNKNOWN'].map(k => (
            <div className="lg-row" key={k}><span className="sym" style={{ background: SEVERITY_RAMP[k], color: SEVERITY_GLYPH_INK[k] }}>AB</span>{SEVERITY_META[k].label}</div>
          ))}
          <div className="xs muted" style={{ marginTop: 6 }}>Letters = category (e.g. AC accident, CL closure, FL flooding). Dark outline = confirmed. Faded = stale. Halo = approximate city-level position.</div>
          <div className="xs muted" style={{ marginTop: 4 }}>Positions are approximate centroids – not exact incident locations and not routed road segments.</div>
        </details>
        {selected && (
          <div className="card map-panel" role="region" aria-label="Selected incident">
            <div className="card-head"><h3>Incident</h3><button className="btn ghost icon-btn" onClick={() => setSelected(null)} aria-label="Close panel"><X size={16} /></button></div>
            <div className="card-body">
              {detail.loading && !detail.data && <Loading />}
              {inc && (
                <div className="stack" style={{ gap: 8 }}>
                  <strong>{inc.title}</strong>
                  <div className="row"><CategoryBadge code={inc.category} /><Severity value={inc.severity} /><StatusBadge status={inc.status} stale={inc.is_stale} /></div>
                  <dl className="kv" style={{ gridTemplateColumns: '110px 1fr' }}>
                    <dt>Location</dt><dd>{[inc.locality, inc.city, inc.state].filter(Boolean).join(', ') || '—'}<div><PrecisionBadge precision={inc.geo_precision} /></div></dd>
                    <dt>Road</dt><dd>{[inc.road_name, inc.highway_number].filter(Boolean).join(' · ') || 'not stated'}</dd>
                    <dt>Event</dt><dd>{inc.event_start ? fmtDate(inc.event_start) : 'start n/a'} → {inc.event_end ? fmtDate(inc.event_end) : 'end n/a'}</dd>
                    <dt>Reported</dt><dd>{fmtDate(inc.first_reported_at)} – {fmtDate(inc.last_reported_at)}</dd>
                    <dt>Verified</dt><dd>{inc.last_verified_at ? fmtDate(inc.last_verified_at) : 'not verified by operator'}</dd>
                    <dt>Confidence</dt><dd>{detail.data.articles[0]?.model_confidence || '—'} (model) · {detail.data.articles.filter((a: any) => a.review_status === 'APPROVED').length} approved report(s)</dd>
                  </dl>
                  {detail.data.articles.slice(0, 3).map((a: any) => (
                    <div key={a.id} className="small">
                      {a.evidence_excerpt && <div className="evidence">“{a.evidence_excerpt}”</div>}
                      <div className="row" style={{ marginTop: 3 }}><span className="muted">{a.source_name} · {fmtDate(a.published_at, false)}</span>
                        {a.source_url && <a className="right" href={a.source_url} target="_blank" rel="noopener noreferrer">Source <ExternalLink size={11} /></a>}</div>
                    </div>
                  ))}
                  <button className="btn primary" onClick={() => setDrawer(inc.id)}>Open full details</button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {drawer && <IncidentDrawer id={drawer} onClose={() => setDrawer(null)} onChanged={() => { geo.reload(); list.reload(); detail.reload() }} />}
    </div>
  )
}

<template>
  <div class="ffp">
    <!-- Header -->
    <div class="ffp-header">
      <h3 class="ffp-title">
        <svg class="ffp-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>
        Fund Flow
      </h3>
      <div class="ffp-toolbar">
        <button class="ffp-tbtn" title="Zoom In" @click="zoomIn">+</button>
        <button class="ffp-tbtn" title="Zoom Out" @click="zoomOut">&minus;</button>
        <button class="ffp-tbtn" title="Reset View" @click="resetView">&#8635;</button>
        <button class="ffp-tbtn" title="Fit All" @click="fitAll">&#9635;</button>
        <div class="ffp-divider"></div>
        <button :class="['ffp-tbtn', { 'ffp-tbtn-active': layoutMode === 'force' }]" title="Force Layout" @click="switchLayout('force')">Force</button>
        <button :class="['ffp-tbtn', { 'ffp-tbtn-active': layoutMode === 'hierarchical' }]" title="Hierarchical Layout" @click="switchLayout('hierarchical')">Hierarchical</button>
        <div class="ffp-divider"></div>
        <button class="ffp-tbtn ffp-export-btn" title="Export as PNG" @click="exportPNG">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          Export PNG
        </button>
        <button class="ffp-tbtn ffp-export-btn" title="Export as SVG" @click="exportSVG">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          Export SVG
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="showEmpty" class="ffp-empty-state">
      <svg class="ffp-empty-icon" viewBox="0 0 48 48" fill="none" stroke="#4a5568" stroke-width="1.5"><circle cx="24" cy="24" r="20"/><path d="M16 24h16M24 16v16" opacity=".4"/></svg>
      <span>No fund flow data available</span>
    </div>

    <!-- Loading -->
    <div v-else-if="isLoadingState" class="ffp-loading">
      <div class="ffp-spinner"></div>
      <span>Analyzing fund flows...</span>
    </div>

    <!-- Error -->
    <div v-else-if="showError && !hasTransfersData" class="ffp-error-state">
      <span>&#9888;</span> {{ store.tokenFlowError }}
    </div>

    <!-- D3 Diagram area -->
    <div v-else ref="containerRef" class="ffp-canvas-wrap">
      <svg ref="svgRef" class="ffp-svg"></svg>
      <div class="ffp-zoom-indicator">{{ zoomPercent }}%</div>
    </div>

    <!-- Legend -->
    <div v-if="legendList.length > 0" class="ffp-legend">
      <span v-for="(item, li) in legendList" :key="'lg'+li" class="ffp-legend-item">
        <span class="ffp-legend-dot" :style="{ backgroundColor: item.color }"></span>
        {{ item.symbol }}
      </span>
    </div>

    <!-- Stats -->
    <div v-if="statsTotal > 0" class="ffp-stats-bar">
      <div class="ffp-stat">
        <span class="ffp-stat-label">Transfers</span>
        <span class="ffp-stat-val">{{ statsTotal }}</span>
      </div>
      <div class="ffp-stat">
        <span class="ffp-stat-label">Addresses</span>
        <span class="ffp-stat-val">{{ statsAddrs }}</span>
      </div>
      <div class="ffp-stat">
        <span class="ffp-stat-label">Tokens</span>
        <span class="ffp-stat-val">{{ statsTokens }}</span>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as d3 from 'd3'
import { useTraceStore } from '@/stores/traceAnalysis.js'

export default {
  name: 'FundFlowPanel',
  props: {
    flows: { type: Array, default: function() { return [] } },
    fundFlowData: { type: Object, default: null }
  },
  setup: function(props) {
    var store = useTraceStore()

    /* ═══════════════════════ CONSTANTS ═══════════════════════ */
    var NODE_W = 220, NODE_H = 68
    var COL_GAP = 400, ROW_GAP = 100, MARGIN = 80
    var PALETTE = [
      '#3b82f6', '#8b5cf6', '#06b6d4', '#10b981',
      '#f59e0b', '#ef4444', '#6366f1', '#ec4899',
      '#84cc16', '#14b8a6', '#f472b6', '#a78bfa'
    ]

    /* ═══════════════════════ REFS ═══════════════════════ */
    var containerRef = ref(null)
    var svgRef = ref(null)
    var layoutMode = ref('force')
    var zoomPercent = ref(100)

    /* D3 internals */
    var simulation = null
    var svg = null
    var gMain = null
    var zoom = null
    var nodeElements = null
    var edgeElements = null
    var labelElements = null
    var flowElements = null
    var gridGroup = null
    var currentTransform = d3.zoomIdentity

    /* ═══════════════════════ DATA SOURCE ═══════════════════════ */
    var rawTransfers = computed(function() {
      var ffd = props.fundFlowData
      if (ffd && ffd.transfers && ffd.transfers.length) return ffd.transfers
      var fl = props.flows
      if (fl && fl.length) {
        var r = []
        for (var i = 0; i < fl.length; i++) {
          var f = fl[i]
          r.push({
            id: i + 1,
            from: f.from || '', to: f.to || f.toAddress || '',
            amount: String(f.amountRaw || f.amount_formatted || 0),
            token: f.tokenAddress || f.token_address || '',
            tokenSymbol: f.tokenSymbol || f.token_symbol || 'Unknown',
            tokenType: 1, isReverted: false
          })
        }
        return r
      }
      return []
    })

    var isLoadingState = computed(function() { return props.flows ? false : store.isTokenFlowLoading })
    var showError = computed(function() { return props.flows ? false : !!store.tokenFlowError })
    var hasTransfersData = computed(function() { return rawTransfers.value.length > 0 })
    var showEmpty = computed(function() { return !hasTransfersData.value && !isLoadingState.value })

    /* ═══════════════════ TOKEN HELPERS ═══════════════════ */
    function tokenSym(t) {
      if (t.token === '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee') return 'ETH'
      if (t.tokenSymbol) return t.tokenSymbol
      if (t.tokenType === 0) return 'ETH'
      if (!t.token || t.token.length <= 10) return t.token || 'ERC20'
      return t.token.slice(0, 6) + '..'
    }

    var tokenColorList = computed(function() {
      var ts = rawTransfers.value, map = {}, arr = [], ci = 0
      for (var i = 0; i < ts.length; i++) {
        if (map[ts[i].token] == null) {
          map[ts[i].token] = ci
          arr.push({ addr: ts[i].token, color: PALETTE[ci % PALETTE.length], idx: ci }); ci++
        }
      }
      return arr
    })

    function tkColor(a) {
      var l = tokenColorList.value
      for (var i = 0; i < l.length; i++) { if (l[i].addr === a) return l[i].color }
      return '#888'
    }

    function tkIdx(a) {
      var l = tokenColorList.value
      for (var i = 0; i < l.length; i++) { if (l[i].addr === a) return l[i].idx }
      return -1
    }

    var legendList = computed(function() {
      var ts = rawTransfers.value, seen = {}, r = []
      for (var i = 0; i < ts.length; i++) {
        if (!seen[ts[i].token]) { seen[ts[i].token] = true; r.push({ symbol: tokenSym(ts[i]), color: tkColor(ts[i].token) }) }
      }
      return r
    })

    /* ═══════════════════ STATS ═══════════════════ */
    var statsTotal = computed(function() { return rawTransfers.value.length })
    var statsAddrs = computed(function() { var s = new Set(), t = rawTransfers.value; for (var i = 0; i < t.length; i++) { s.add(t[i].from); s.add(t[i].to) } return s.size })
    var statsTokens = computed(function() { var s = new Set(), t = rawTransfers.value; for (var i = 0; i < t.length; i++) s.add(t[i].token); return s.size })

    /* ═══════════════════ GRAPH DATA BUILDERS ═══════════════════ */

    /** Build nodes array from transfers using topological sort for layering */
    function buildNodes(transfers) {
      if (!transfers.length) return []
      var nm = {}, inD = {}, outE = {}
      function ensure(a) {
        if (!nm[a]) { nm[a] = { id: a, address: a, fullAddress: a, layer: -1, inCnt: 0, outCnt: 0 }; inD[a] = 0; outE[a] = [] }
      }
      for (var i = 0; i < transfers.length; i++) {
        ensure(transfers[i].from); ensure(transfers[i].to)
        nm[transfers[i].from].outCnt++; nm[transfers[i].to].inCnt++
        outE[transfers[i].from].push(transfers[i].to); inD[transfers[i].to]++
      }
      // BFS topological sort for layers
      var q = [], keys = Object.keys(nm)
      for (var i = 0; i < keys.length; i++) { if (inD[keys[i]] === 0) { q.push(keys[i]); nm[keys[i]].layer = 0 } }
      var qi = 0
      while (qi < q.length) {
        var c = q[qi++], oe = outE[c] || []
        for (var j = 0; j < oe.length; j++) {
          nm[oe[j]].layer = Math.max(nm[oe[j]].layer, nm[c].layer + 1); inD[oe[j]]--; if (inD[oe[j]] === 0) q.push(oe[j])
        }
      }
      var mL = 0
      for (var i = 0; i < keys.length; i++) { if (nm[keys[i]].layer > mL) mL = nm[keys[i]].layer }
      for (var i = 0; i < keys.length; i++) { if (nm[keys[i]].layer < 0) nm[keys[i]].layer = mL + 1 }

      // Compute visual properties
      var placed = []
      for (var i = 0; i < keys.length; i++) {
        var n = nm[keys[i]]
        n.roleLabel = n.outCnt > 0 && n.inCnt === 0 ? 'Sender' : (n.inCnt > 0 && n.outCnt === 0 ? 'Receiver' : '')
        n.shortAddr = keys[i].length > 12 ? keys[i].slice(0, 8) + '..' + keys[i].slice(-4) : keys[i]
        var h = 0, alen = Math.min(keys[i].length, 10), hues = ['#6366f1','#8b5cf6','#ec4899','#f43f5e','#f97316','#eab308','#22c55e','#14b8a6','#06b6d4','#3b82f6']
        for (var k = 0; k < alen; k++) h = keys[i].charCodeAt(k) + ((h << 5) - h)
        n.avatarColor = hues[Math.abs(h) % hues.length]
        n.avatarLetter = keys[i].slice(2, 4).toUpperCase()
        placed.push(n)
      }
      return placed
    }

    /** Build edges array from transfers with D3-compatible structure */
    function buildEdges(transfers, nodeMap) {
      if (!transfers.length || !nodeMap) return []
      var edges = []
      for (var i = 0; i < transfers.length; i++) {
        var tr = transfers[i]
        var src = nodeMap[tr.from], dst = nodeMap[tr.to]
        if (!src || !dst) continue
        edges.push({
          id: tr.id,
          source: src.id,
          target: dst.id,
          from: tr.from,
          to: tr.to,
          amount: tr.amount,
          token: tr.token,
          color: tkColor(tr.token)
        })
      }
      return edges
    }

    /* Build adjacency map: addr -> set of connected edge IDs */
    function buildNodeEdgeMap(edges) {
      var m = {}
      for (var i = 0; i < edges.length; i++) {
        var e = edges[i]
        if (!m[e.source]) m[e.source] = []; m[e.source].push(e.id)
        if (!m[e.target]) m[e.target] = []; m[e.target].push(e.id)
      }
      return m
    }

    /* ═══════════════════ HELPERS ═══════════════════ */
    function roleBadgeColor(r) { if (r === 'Sender') return '#3b82f6'; if (r === 'Receiver') return '#a78bfa'; return '#6b7280' }

    function fmtAmt(raw) {
      if (!raw) return '0'; var s = String(raw), num = parseFloat(s.replace(/,/g, ''))
      if (isNaN(num)) return s
      if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(2) + 'B'
      if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(2) + 'M'
      if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(2) + 'K'
      if (Math.abs(num) >= 100) return Math.round(num).toLocaleString()
      if (Math.abs(num) >= 1) return parseFloat(num.toFixed(4)).toLocaleString()
      if (num === 0) return '0'; if (Math.abs(num) < 0.001) return '<0.001'
      return parseFloat(num.toFixed(6)).toString()
    }

    /* ═══════════════════ D3 RENDER CORE ═══════════════════ */

    function initSVG() {
      if (!containerRef.value || !svgRef.value) return
      var rect = containerRef.value.getBoundingClientRect()
      var w = rect.width || 1200
      var h = 600

      svg = d3.select(svgRef.value)
        .attr('width', w)
        .attr('height', h)
        .attr('viewBox', '0 0 ' + w + ' ' + h)

      // Defs: markers, filters
      var defs = svg.append('defs')

      // Arrow markers per token color
      defs.append('marker')
        .attr('id', 'arrow-default')
        .attr('markerUnits', 'userSpaceOnUse')
        .attr('markerWidth', 18)
        .attr('markerHeight', 14)
        .attr('refX', 16)
        .attr('refY', 7)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M 0 1 L 18 7 L 0 13 L 5 7 z')
        .attr('fill', '#6b7280')

      var tcl = tokenColorList.value
      for (var ti = 0; ti < tcl.length; ti++) {
        defs.append('marker')
          .attr('id', 'arrow-' + tcl[ti].idx)
          .attr('markerUnits', 'userSpaceOnUse')
          .attr('markerWidth', 18)
          .attr('markerHeight', 14)
          .attr('refX', 16)
          .attr('refY', 7)
          .attr('orient', 'auto')
          .append('path')
          .attr('d', 'M 0 1 L 18 7 L 0 13 L 5 7 z')
          .attr('fill', tcl[ti].color)
      }

      // Glow filter
      var glowFilter = defs.append('filter').attr('id', 'glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%')
      glowFilter.append('feGaussianBlur').attr('stdDeviation', 4).attr('result', 'blur')
      glowFilter.append('feMerge').append('feMergeNode').attr('in', 'blur')
      glowFilter.select('feMerge').append('feMergeNode').attr('in', 'SourceGraphic')

      // Node shadow
      var shadowFilter = defs.append('filter').attr('id', 'nShadow').attr('x', '-30%').attr('y', '-30%').attr('width', '160%').attr('height', '160%')
      shadowFilter.append('feDropShadow').attr('dx', 0).attr('dy', 3).attr('stdDeviation', 5).attr('flood-color', '#000').attr('flood-opacity', 0.4)

      // Label shadow
      var labelShadow = defs.append('filter').attr('id', 'lShadow').attr('x', '-20%').attr('y', '-50%').attr('width', '140%').attr('height', '200%')
      labelShadow.append('feDropShadow').attr('dx', 0).attr('dy', 2).attr('stdDeviation', 3).attr('flood-color', '#000').attr('flood-opacity', 0.55)

      // Zoom behavior
      zoom = d3.zoom()
        .scaleExtent([0.15, 4])
        .on('zoom', function(event) {
          currentTransform = event.transform
          gMain.attr('transform', event.transform)
          zoomPercent.value = Math.round(event.transform.k * 100)
        })

      svg.call(zoom)

      // Main group
      gMain = svg.append('g').attr('class', 'ffp-main-group')

      // Layer 1: Grid dots
      gridGroup = gMain.append('g').attr('class', 'ffp-grid-layer').attr('pointer-events', 'none')
      renderGrid(w, h)

      // Layer 2: Edges group
      gMain.append('g').attr('class', 'ffp-edge-layer').attr('pointer-events', 'none')

      // Layer 3: Nodes group
      gMain.append('g').attr('class', 'ffp-node-layer')

      // Layer 4: Labels group
      gMain.append('g').attr('class', 'ffp-label-layer').attr('pointer-events', 'none')
    }

    function renderGrid(w, h) {
      if (!gridGroup) return
      gridGroup.selectAll('*').remove()
      var step = 24, dots = []
      for (var x = step; x < w; x += step) {
        for (var y = step; y < h; y += step) {
          dots.push({ x: x, y: y })
        }
      }
      gridGroup.selectAll('circle')
        .data(dots)
        .enter()
        .append('circle')
        .attr('cx', function(d) { return d.x })
        .attr('cy', function(d) { return d.y })
        .attr('r', 1.2)
        .attr('fill', '#21262d')
        .attr('opacity', 0.45)
    }

    /** Render the complete graph with D3 */
    function renderGraph() {
      if (!svg || !gMain) return
      var ts = rawTransfers.value
      if (!ts.length) return

      // Stop existing simulation
      if (simulation) {
        simulation.stop()
        simulation = null
      }

      // Build data
      var nodes = buildNodes(ts)
      var nodeMap = {}
      for (var ni = 0; ni < nodes.length; ni++) { nodeMap[nodes[ni].id] = nodes[ni] }
      var edges = buildEdges(ts, nodeMap)
      var nodeEdgeMap = buildNodeEdgeMap(edges)

      // Assign initial positions based on hierarchical layout
      assignInitialPositions(nodes, layoutMode.value)

      // Deep clone nodes for D3 (it mutates objects)
      var d3Nodes = nodes.map(function(n) { return Object.assign({}, n) })
      var d3Edges = edges.map(function(e) { return Object.assign({}, e) })

      // Rebuild node map for cloned nodes
      var d3NodeMap = {}
      for (var i = 0; i < d3Nodes.length; i++) { d3NodeMap[d3Nodes[i].id] = d3Nodes[i] }

      /* ═══ PARALLEL EDGE OFFSET ALGORITHM ═══
       * Groups edges by (source, target) pair.
       * For each group with N>1 edges, assigns:
       *   - parallelIndex: 0-based ordinal within the group
       *   - parallelTotal: total count in the group
       *   - parallelOffset: signed distance from center line (-N/2 .. +N/2)
       * This allows bezier curves to fan out and labels to avoid overlap.
       */
      var parallelGroups = {}
      for (var ei = 0; ei < d3Edges.length; ei++) {
        var pk = d3Edges[ei].from + '||' + d3Edges[ei].to
        if (!parallelGroups[pk]) parallelGroups[pk] = []
        parallelGroups[pk].push(d3Edges[ei])
      }
      var SPREAD = 36  // pixels between adjacent parallel edges
      var pgKeys = Object.keys(parallelGroups)
      for (var gi = 0; gi < pgKeys.length; gi++) {
        var group = parallelGroups[pgKeys[gi]], gt = group.length
        for (var pi = 0; pi < gt; pi++) {
          group[pi]._pIdx = pi
          group[pi]._pTotal = gt
          group[pi]._pOffset = (pi - (gt - 1) / 2) * SPREAD
        }
      }

      // Clear previous elements
      gMain.select('.ffp-edge-layer').selectAll('*').remove()
      gMain.select('.ffp-node-layer').selectAll('*').remove()
      gMain.select('.ffp-label-layer').selectAll('*').remove()

      var edgeLayer = gMain.select('.ffp-edge-layer')
      var nodeLayer = gMain.select('.ffp-node-layer')
      var labelLayer = gMain.select('.ffp-label-layer')

      /* ---- EDGES (paths + animated flow overlays) ---- */
      
      // Base edge paths — always visible, static arrows
      edgeElements = edgeLayer.selectAll('.ffp-edge-group')
        .data(d3Edges, function(d) { return d.id })
        .enter()
        .append('g')
        .attr('class', 'ffp-edge-group')
        .style('cursor', 'pointer')

      // Layer 1: Base visible path (always shows direction)
      // Use stroke-opacity instead of opacity so marker-end arrow stays fully opaque
      edgeElements.append('path')
        .attr('class', 'ffp-edge-base')
        .attr('stroke', function(d) { return d.color })
        .attr('stroke-width', 2)
        .attr('fill', 'none')
        .attr('stroke-opacity', 0.65)
        .attr('marker-end', function(d) {
          var ti = tkIdx(d.token)
          return ti >= 0 ? '#arrow-' + ti : '#arrow-default'
        })

      // Layer 2: Glow overlay (hidden by default, shown on hover)
      edgeElements.append('path')
        .attr('class', 'ffp-edge-glow')
        .attr('stroke', function(d) { return d.color })
        .attr('stroke-width', 3)
        .attr('fill', 'none')
        .attr('opacity', 0)
        .attr('filter', 'url(#glow)')

      // Layer 3: Animated particle container group (one group per edge)
      var particleGroups = edgeElements.append('g').attr('class', 'ffp-particle-group')

      /* ---- NODES (card-style rectangles) ---- */
      nodeElements = nodeLayer.selectAll('.ffp-node-group')
        .data(d3Nodes, function(d) { return d.id })
        .enter()
        .append('g')
        .attr('class', 'ffp-node-group')
        .attr('cursor', 'grab')
        .call(d3.drag()
          .on('start', dragStarted)
          .on('drag', dragged)
          .on('end', dragEnded))

      // Node card background
      nodeElements.append('rect')
        .attr('class', 'ffp-node-card')
        .attr('width', NODE_W)
        .attr('height', NODE_H)
        .attr('rx', 10)
        .attr('fill', '#161b22')
        .attr('stroke', '#2d333b')
        .attr('stroke-width', 1)
        .attr('filter', 'url(#nShadow)')

      // Role badge group (conditional)
      var roleGroups = nodeElements.filter(function(d) { return d.roleLabel })
        .append('g')
        .attr('transform', 'translate(10, 9)')

      roleGroups.append('rect')
        .attr('width', 52)
        .attr('height', 18)
        .attr('rx', 9)
        .attr('fill', function(d) { return roleBadgeColor(d.roleLabel) })
        .attr('opacity', 0.12)

      roleGroups.append('text')
        .attr('x', 26)
        .attr('y', 13)
        .attr('text-anchor', 'middle')
        .attr('fill', function(d) { return roleBadgeColor(d.roleLabel) })
        .attr('font-size', 9)
        .attr('font-weight', 700)
        .text(function(d) { return d.roleLabel })

      // Avatar circle
      nodeElements.append('circle')
        .attr('class', 'ffp-avatar')
        .attr('cx', 24)
        .attr('cy', 40)
        .attr('r', 13)
        .attr('fill', function(d) { return d.avatarColor })

      // Avatar letter
      nodeElements.append('text')
        .attr('class', 'ffp-avatar-letter')
        .attr('x', 24)
        .attr('y', 44)
        .attr('text-anchor', 'middle')
        .attr('fill', '#fff')
        .attr('font-size', 10)
        .attr('font-weight', 700)
        .text(function(d) { return d.avatarLetter })

      // Address text
      nodeElements.append('text')
        .attr('class', 'ffp-addr-text')
        .attr('x', 44)
        .attr('y', 44)
        .attr('fill', '#8b949e')
        .attr('font-size', 11)
        .attr('font-family', "'JetBrains Mono', monospace")
        .attr('font-weight', 500)
        .text(function(d) { return d.shortAddr })

      // Tooltip foreignObject
      nodeElements.append('foreignObject')
        .attr('class', 'ffp-tooltip-fo')
        .attr('x', -40)
        .attr('y', NODE_H + 8)
        .attr('width', 300)
        .attr('height', 28)
        .attr('opacity', 0)
        .append('xhtml:div')
        .attr('xmlns', 'http://www.w3.org/1999/xhtml')
        .html('<div style="display:flex;align-items:center;justify-content:center;height:100%"><span class="ffp-tooltip-text-d3"></span></div>')

      /* ---- EDGE LABELS ---- */
      labelElements = labelLayer.selectAll('.ffp-label-group')
        .data(d3Edges, function(d) { return d.id })
        .enter()
        .append('g')
        .attr('class', 'ffp-label-group')
        .attr('pointer-events', 'all')
        .style('cursor', 'default')

      labelElements.append('rect')
        .attr('class', 'ffp-label-bg')
        .attr('x', 0)
        .attr('y', -11)
        .attr('rx', 5)
        .attr('fill', '#161b22')
        .attr('stroke', '#30363d')
        .attr('stroke-width', 0.8)
        .attr('filter', 'url(#lShadow)')
        .attr('opacity', 0.92)

      labelElements.append('text')
        .attr('class', 'ffp-label-text')
        .attr('x', 0)
        .attr('y', 1)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('font-size', 10.5)
        .attr('font-weight', 600)
        .attr("font-family", "Inter, sans-serif")

      /* ---- INTERACTION HANDLERS ---- */
      // Node hover
      nodeElements
        .on('mouseenter', function(event, d) {
          handleNodeHover(d, d3Edges, d3NodeMap, nodeEdgeMap)
        })
        .on('mouseleave', function() {
          handleHoverEnd()
        })

      // Edge hover (on the group, not just labels)
      edgeElements
        .on('mouseenter', function(event, d) {
          event.stopPropagation()
          handleEdgeHover(d, d3Nodes, d3NodeMap, nodeEdgeMap)
        })
        .on('mouseleave', function(event) {
          event.stopPropagation()
          handleHoverEnd()
        })

      labelElements
        .on('mouseenter', function(event, d) {
          event.stopPropagation()
          handleEdgeHover(d, d3Nodes, d3NodeMap, nodeEdgeMap)
        })
        .on('mouseleave', function(event) {
          event.stopPropagation()
          handleHoverEnd()
        })

      /* ── FORCE SIMULATION ── */
      if (layoutMode.value === 'force') {
        startForceSimulation(d3Nodes, d3Edges, d3NodeMap)
      } else {
        // Hierarchical: just position and render, no simulation
        updatePositions(d3Nodes, d3Edges, d3NodeMap)
      }
    }

    /** Assign initial positions based on layout mode */
    function assignInitialPositions(nodes, mode) {
      if (mode === 'hierarchical') {
        // Topological layered layout (BFS-based)
        var ly = {}
        for (var i = 0; i < nodes.length; i++) {
          var L = nodes[i].layer
          if (!ly[L]) ly[L] = []
          ly[L].push(nodes[i])
        }
        var lk = Object.keys(ly).map(Number).sort(function(a, b) { return a - b })
        var mr = 0
        for (var li = 0; li < lk.length; li++) {
          if (ly[lk[li]].length > mr) mr = ly[lk[li]].length
        }
        for (var li = 0; li < lk.length; li++) {
          var mems = ly[lk[li]], rc = mems.length, sy = MARGIN
          if (rc < mr) sy += Math.floor((mr - rc) * (NODE_H + ROW_GAP) / 2)
          for (var mi = 0; mi < mems.length; mi++) {
            mems[mi].fx = MARGIN + lk[li] * COL_GAP
            mems[mi].fy = sy + mi * (NODE_H + ROW_GAP)
            mems[mi].x = mems[mi].fx
            mems[mi].y = mems[mi].fy
          }
        }
      } else {
        // Force mode: spread initial positions radially
        var cx = 600, cy = 300
        for (var i = 0; i < nodes.length; i++) {
          var angle = (2 * Math.PI * i) / nodes.length
          var radius = 180 + Math.random() * 120
          nodes[i].x = cx + radius * Math.cos(angle)
          nodes[i].y = cy + radius * Math.sin(angle)
          nodes[i].fx = null
          nodes[i].fy = null
        }
      }
    }

    /** Start D3 force simulation */
    function startForceSimulation(d3Nodes, d3Edges, d3NodeMap) {
      simulation = d3.forceSimulation(d3Nodes)
        .force('link', d3.forceLink(d3Edges)
          .id(function(d) { return d.id })
          .distance(COL_GAP * 0.85)
          .strength(0.35))
        .force('charge', d3.forceManyBody()
          .strength(-400)
          .distanceMax(600))
        .force('center', d3.forceCenter(600, 300))
        .force('collision', d3.forceCollide().radius(function(d) { return NODE_W / 2 + 30 }).strength(0.8))
        .force('x', d3.forceX().strength(0.08))
        .force('y', d3.forceY().strength(0.08))
        .alphaDecay(0.02)
        .velocityDecay(0.45)
        .on('tick', function() {
          updatePositions(d3Nodes, d3Edges, d3NodeMap)
        })

      // Auto-stop after stabilization
      setTimeout(function() {
        if (simulation) {
          simulation.alphaTarget(0).alpha(0.01)
          setTimeout(function() {
            if (simulation) {
              simulation.stop()
              // Final tick to snap positions
              updatePositions(d3Nodes, d3Edges, d3NodeMap)
            }
          }, 1500)
        }
      }, 8000)
    }

    /** Update all element positions on each tick */
    function updatePositions(d3Nodes, d3Edges, d3NodeMap) {
      if (!nodeElements || !edgeElements) return

      // Update node positions
      nodeElements.attr('transform', function(d) {
        return 'translate(' + (d.x - NODE_W / 2) + ',' + (d.y - NODE_H / 2) + ')'
      })

      // Update tooltip text positions
      nodeElements.select('.ffp-tooltip-fo span')
        .text(function(d) { return d.fullAddress })

      // Update edge paths (bezier curves with parallel-edge separation)
      edgeElements.each(function(edgeData) {
        // D3 force simulation converts source/target from string IDs to node objects
        var srcId = typeof edgeData.source === 'object' ? edgeData.source.id : edgeData.source
        var dstId = typeof edgeData.target === 'object' ? edgeData.target.id : edgeData.target
        var src = d3NodeMap[srcId]
        var dst = d3NodeMap[dstId]
        if (!src || !dst) return
        var el = d3.select(this)

        // Parallel edge offset: separate multiple edges between same node pair
        var pOff = edgeData._pOffset || 0
        var pTotal = edgeData._pTotal || 1

        var sx = src.x + NODE_W / 2, sy = src.y
        var dx = dst.x - NODE_W / 2, dy = dst.y
        var dist = dx - sx
        var ctrlDist = Math.min(Math.abs(dist) * 0.45, 140)
        var cp1x = sx + ctrlDist, cp1y = sy
        var cp2x = dx - ctrlDist * 0.7, cp2y = dy

        // Offset the control point midY to create curved fan-out for parallel edges
        var baseMidX = (sx + dx) / 2, baseMidY = (sy + dy) / 2
        var midX = baseMidX + pOff * 0.15
        var midY = baseMidY + pOff

        // For edges spanning multiple layers, add extra spread proportional to layer gap
        var layerDiff = Math.abs((src.layer || 0) - (dst.layer || 0))
        if (layerDiff > 1 && pTotal > 1) {
          var extraPush = (layerDiff - 1) * 25
          midY += (pOff > 0 ? 1 : -1) * extraPush * 0.5
        }

        // Arrow gap: shorten the line significantly so arrow tip sits well outside target node border
        var ARROW_GAP = 18
        var angle = Math.atan2(dy - midY, dx - midX)
        var ex = dx - ARROW_GAP * Math.cos(angle), ey = dy - ARROW_GAP * Math.sin(angle)

        var pathD = 'M' + sx.toFixed(1) + ',' + sy.toFixed(1) +
          ' C' + cp1x.toFixed(1) + ',' + (cp1y + pOff * 0.3).toFixed(1) +
          ' ' + midX.toFixed(1) + ',' + midY.toFixed(1) +
          ' ' + cp2x.toFixed(1) + ',' + (cp2y + pOff * 0.3).toFixed(1) +
          ' L' + ex.toFixed(1) + ',' + ey.toFixed(1)

        el.select('.ffp-edge-base').attr('d', pathD)
        el.select('.ffp-flow-line').attr('d', pathD)

        // Arrow marker on carrier path
        var ti = tkIdx(edgeData.token)
        var markerId = ti >= 0 ? '#arrow-' + ti : '#arrow-default'
        el.select('.ffp-arrow-carrier')
          .attr('d', pathD)
          .attr('marker-end', markerId)
      })

      // Update label positions (with parallel-edge offset separation)
      labelElements.each(function(edgeData) {
        var srcId = typeof edgeData.source === 'object' ? edgeData.source.id : edgeData.source
        var dstId = typeof edgeData.target === 'object' ? edgeData.target.id : edgeData.target
        var src = d3NodeMap[srcId]
        var dst = d3NodeMap[dstId]
        if (!src || !dst) return
        var el = d3.select(this)

        var pOff = edgeData._pOffset || 0

        var sx = src.x + NODE_W / 2, sy = src.y
        var dx = dst.x - NODE_W / 2, dy = dst.y
        // Label sits at the midpoint of the curve, offset by the parallel spread
        var lx = (sx + dx) / 2 + pOff * 0.1
        var ly = (sy + dy) / 2 - 16 + pOff * 0.9
        if (ly < 30) ly = 30

        var amtTxt = fmtAmt(edgeData.amount), symTxt = 'ETH'
        for (var ti = 0; ti < rawTransfers.value.length; ti++) {
          if (rawTransfers.value[ti].id === edgeData.id) {
            symTxt = tokenSym(rawTransfers.value[ti])
            break
          }
        }
        var lbl = '[' + edgeData.id + '] ' + amtTxt + ' ' + symTxt
        var lw = Math.max(lbl.length * 6.8, 85)

        el.attr('transform', 'translate(' + lx.toFixed(1) + ',' + ly.toFixed(1) + ')')
          .select('.ffp-label-bg')
          .attr('width', lw + 16)
        el.select('.ffp-label-text')
          .attr('fill', edgeData.color)
          .text(lbl)
      })
    }

    /* ═══════════════════ DRAG HANDLERS ═══════════════════ */
    function dragStarted(event, d) {
      if (!event.active && simulation) simulation.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
      d3.select(this).raise().select('.ffp-node-card').style('cursor', 'grabbing')
    }

    function dragged(event, d) {
      d.fx = event.x
      d.fy = event.y
      // Re-render during drag
      var d3Nodes = nodeElements.data()
      var d3Edges = edgeElements ? edgeElements.data() : []
      var d3NodeMap = {}
      for (var i = 0; i < d3Nodes.length; i++) { d3NodeMap[d3Nodes[i].id] = d3Nodes[i] }
      updatePositions(d3Nodes, d3Edges, d3NodeMap)
    }

    function dragEnded(event, d) {
      if (!event.active && simulation) simulation.alphaTarget(0)
      if (layoutMode.value !== 'hierarchical') {
        d.fx = null
        d.fy = null
      }
      d3.select(this).select('.ffp-node-card').style('cursor', 'grab')
    }

    /* ════════ PARTICLE ANIMATION ENGINE ════════ */
    var activeParticleTimers = {}

    /** Start particles flowing along a specific edge's path */
    function startParticles(edgeData) {
      if (activeParticleTimers[edgeData.id]) return
      // Get current path d from the DOM
      var group = edgeElements.filter(function(d) { return d.id === edgeData.id })
      if (group.empty()) return
      var basePathD = group.select('.ffp-edge-base').attr('d')
      if (!basePathD) return

      var pGroup = group.select('.ffp-particle-group')
      pGroup.selectAll('*').remove()

      // Create 3-5 small circle particles that travel along the path
      var numParticles = Math.min(4, Math.max(2, Math.ceil(basePathD.length / 200)))
      for (var i = 0; i < numParticles; i++) {
        pGroup.append('circle')
          .attr('class', 'ffp-particle')
          .attr('r', 3)
          .attr('fill', edgeData.color)
          .attr('filter', 'url(#glow)')
      }

      // Animate particles along the path using getPointAtLength
      var duration = 1200 + Math.random() * 400
      var startTime = null
      var pathEl = null
      // Create a temporary SVG path element to use getPointAtLength
      try {
        pathEl = svgRef.value.querySelector('path[d="' + basePathD.replace(/"/g, "'") + '"]')
        if (!pathEl) {
          // Fallback: create off-screen path
          pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path')
          pathEl.setAttribute('d', basePathD)
        }
      } catch(e) { return }

      var totalLen = pathEl.getTotalLength ? pathEl.getTotalLength() : 500

      activeParticleTimers[edgeData.id] = true

      function animateParticles(timestamp) {
        if (!activeParticleTimers[edgeData.id]) return
        if (!startTime) startTime = timestamp
        var elapsed = timestamp - startTime
        // Each particle has a different phase offset
        pGroup.selectAll('.ffp-particle').each(function(d, idx) {
          var phase = ((elapsed / duration) + idx / numParticles) % 1
          var len = phase * totalLen
          var pt
          if (pathEl.getPointAtLength) {
            try { pt = pathEl.getPointAtLength(len) } catch(e) { pt = null }
          } else {
            pt = { x: 0, y: 0 }
          }
          if (pt) {
            d3.select(this).attr('cx', pt.x).attr('cy', pt.y)
              .attr('opacity', 0.7 + 0.3 * Math.sin(phase * Math.PI))
          }
        })
        requestAnimationFrame(animateParticles)
      }
      requestAnimationFrame(animateParticles)
    }

    /** Stop all particle animations */
    function stopAllParticles() {
      Object.keys(activeParticleTimers).forEach(function(key) {
        activeParticleTimers[key] = false
      })
      activeParticleTimers = {}
      if (edgeElements) {
        edgeElements.select('.ffp-particle-group').selectAll('*').remove()
      }
    }

    /* ═══════════════════ INTERACTION: HOVER ═══════════════════ */
    function handleNodeHover(hoveredNodeData, allEdges, nodeMap, neMap) {
      var hoveredAddr = hoveredNodeData.address
      var connectedIds = neMap[hoveredAddr] || []

      // Highlight connected edges — base path brightens, glow overlay appears
      edgeElements.select('.ffp-edge-base')
        .transition().duration(150)
        .attr('stroke-opacity', function(d) {
          return connectedIds.indexOf(d.id) !== -1 ? 1 : 0.08
        })
        .attr('stroke-width', function(d) {
          return connectedIds.indexOf(d.id) !== -1 ? 2.5 : 1.5
        })

      edgeElements.select('.ffp-edge-glow')
        .transition().duration(150)
        .attr('opacity', function(d) {
          return connectedIds.indexOf(d.id) !== -1 ? 0.9 : 0
        })

      // Start particles on connected edges, stop on others
      for (var ei = 0; ei < allEdges.length; ei++) {
        if (connectedIds.indexOf(allEdges[ei].id) !== -1) {
          startParticles(allEdges[ei])
        }
      }

      // Highlight this node and connected nodes
      var connectedAddrs = new Set([hoveredAddr])
      for (var ei = 0; ei < allEdges.length; ei++) {
        if (connectedIds.indexOf(allEdges[ei].id) !== -1) {
          connectedAddrs.add(allEdges[ei].from)
          connectedAddrs.add(allEdges[ei].to)
        }
      }

      nodeElements
        .classed('ffp-node-active', function(d) { return connectedAddrs.has(d.address) })
        .select('.ffp-node-card')
        .transition().duration(150)
        .attr('fill', function(d) {
          if (d.address === hoveredAddr) return '#1a2234'
          if (connectedAddrs.has(d.address)) return '#151b24'
          return '#161b22'
        })
        .attr('stroke', function(d) {
          if (d.address === hoveredAddr) return getHighlightColor(d, allEdges, connectedIds)
          if (connectedAddrs.has(d.address)) return '#38404c'
          return '#2d333b'
        })
        .attr('stroke-width', function(d) {
          return d.address === hoveredAddr ? 2.5 : (connectedAddrs.has(d.address) ? 1.5 : 1)
        })
        .attr('filter', function(d) {
          return d.address === hoveredAddr ? 'url(#glow)' : 'url(#nShadow)'
        })

      // Show tooltip
      nodeElements.select('.ffp-tooltip-fo')
        .transition().duration(150)
        .attr('opacity', function(d) { return d.address === hoveredAddr ? 1 : 0 })

      // Dim unrelated labels
      labelElements
        .transition().duration(150)
        .attr('opacity', function(d) { return connectedIds.indexOf(d.id) !== -1 ? 1 : 0.15 })
    }

    function handleEdgeHover(hoveredEdgeData, allNodes, nodeMap, neMap) {
      var hoveredId = hoveredEdgeData.id
      var relatedAddrs = [hoveredEdgeData.from, hoveredEdgeData.to]

      // Highlight this edge only — base brightens + glow overlay appears
      edgeElements.select('.ffp-edge-base')
        .transition().duration(150)
        .attr('stroke-opacity', function(d) { return d.id === hoveredId ? 1 : 0.08 })
        .attr('stroke-width', function(d) { return d.id === hoveredId ? 2.5 : 1.5 })

      edgeElements.select('.ffp-edge-glow')
        .transition().duration(150)
        .attr('opacity', function(d) { return d.id === hoveredId ? 0.9 : 0 })

      // Start particle animation on this edge
      startParticles(hoveredEdgeData)

      // Highlight source and target nodes
      nodeElements
        .classed('ffp-node-active', function(d) { return relatedAddrs.indexOf(d.address) !== -1 })
        .select('.ffp-node-card')
        .transition().duration(150)
        .attr('fill', function(d) {
          return relatedAddrs.indexOf(d.address) !== -1 ? '#1a2234' : '#161b22'
        })
        .attr('stroke', function(d) {
          if (relatedAddrs.indexOf(d.address) !== -1) return hoveredEdgeData.color
          return '#2d333b'
        })
        .attr('stroke-width', function(d) {
          return relatedAddrs.indexOf(d.address) !== -1 ? 2.5 : 1
        })
        .attr('filter', function(d) {
          return relatedAddrs.indexOf(d.address) !== -1 ? 'url(#glow)' : 'url(#nShadow)'
        })

      // Highlight this label
      labelElements
        .transition().duration(150)
        .attr('opacity', function(d) { return d.id === hoveredId ? 1 : 0.15 })
        .select('.ffp-label-bg')
        .attr('opacity', function(d) { return d.id === hoveredId ? 1 : 0.92 })
    }

    function handleHoverEnd() {
      if (!edgeElements || !nodeElements || !labelElements) return

      // Stop all particle animations
      stopAllParticles()

      // Reset edges — base path back to normal, hide glow
      edgeElements.select('.ffp-edge-base')
        .transition().duration(200)
        .attr('stroke-opacity', 0.65)
        .attr('stroke-width', 2)

      edgeElements.select('.ffp-edge-glow')
        .transition().duration(200)
        .attr('opacity', 0)

      // Reset nodes
      nodeElements
        .classed('ffp-node-active', false)
        .select('.ffp-node-card')
        .transition().duration(200)
        .attr('fill', '#161b22')
        .attr('stroke', '#2d333b')
        .attr('stroke-width', 1)
        .attr('filter', 'url(#nShadow)')

      nodeElements.select('.ffp-tooltip-fo')
        .transition().duration(200)
        .attr('opacity', 0)

      // Reset labels
      labelElements
        .transition().duration(200)
        .attr('opacity', 1)
        .select('.ffp-label-bg')
        .attr('opacity', 0.92)
    }

    function getHighlightColor(nodeData, allEdges, activeEdgeIds) {
      for (var i = 0; i < activeEdgeIds.length; i++) {
        for (var j = 0; j < allEdges.length; j++) {
          if (allEdges[j].id === activeEdgeIds[i] &&
             (allEdges[j].from === nodeData.address || allEdges[j].to === nodeData.address)) {
            return allEdges[j].color
          }
        }
      }
      return '#58a6ff'
    }

    /* ═══════════════════ ZOOM/PAN CONTROLS ═══════════════════ */
    function zoomIn() {
      if (!svg || !zoom) return
      svg.transition().duration(300).call(zoom.scaleBy, 1.25)
    }

    function zoomOut() {
      if (!svg || !zoom) return
      svg.transition().duration(300).call(zoom.scaleBy, 0.8)
    }

    function resetView() {
      if (!svg || !zoom) return
      svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity)
      zoomPercent.value = 100
    }

    function fitAll() {
      if (!containerRef.value || !svg || !zoom) return
      var d3n = nodeElements ? nodeElements.data() : []
      if (!d3n.length) return
      var rect = containerRef.value.getBoundingClientRect(), pad = 80
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      for (var i = 0; i < d3n.length; i++) {
        if (d3n[i].x < minX) minX = d3n[i].x
        if (d3n[i].y < minY) minY = d3n[i].y
        if (d3n[i].x + NODE_W > maxX) maxX = d3n[i].x + NODE_W
        if (d3n[i].y + NODE_H > maxY) maxY = d3n[i].y + NODE_H
      }
      var gw = Math.max(maxX - minX + pad * 2, 400)
      var gh = Math.max(maxY - minY + pad * 2, 300)
      var s = Math.min((rect.width - pad * 2) / gw, (rect.height - pad * 2) / gh)
      s = Math.max(0.15, Math.min(s, 4))
      var cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
      var tx = rect.width / 2 - cx * s
      var ty = rect.height / 2 - cy * s
      var transform = d3.zoomIdentity.translate(tx, ty).scale(s)
      svg.transition().duration(500).call(zoom.transform, transform)
    }

    function switchLayout(mode) {
      layoutMode.value = mode
      renderGraph()
    }

    /* ═══════════════════ EXPORT ═══════════════════ */
    function exportPNG() {
      var el = svgRef.value
      if (!el) return
      try {
        var ser = new XMLSerializer(), svgStr = ser.serializeToString(el)
        var blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' })
        var url = URL.createObjectURL(blob), img = new Image()
        img.onload = function() {
          var cv = document.createElement('canvas'), sv = 2
          cv.width = 1600 * sv; cv.height = 600 * sv
          var ctx = cv.getContext('2d')
          ctx.scale(sv, sv)
          ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, 1600, 600)
          ctx.drawImage(img, 0, 0, 1600, 600)
          cv.toBlob(function(b) {
            if (!b) return
            var link = document.createElement('a')
            link.download = 'fundflow_' + Date.now() + '.png'
            link.href = URL.createObjectURL(b); link.click()
            URL.revokeObjectURL(link.href)
          }, 'image/png')
          URL.revokeObjectURL(url)
        }
        img.src = url
      } catch(err) { console.error('PNG export error:', err) }
    }

    function exportSVG() {
      var el = svgRef.value
      if (!el) return
      try {
        var ser = new XMLSerializer(), svgStr = ser.serializeToString(el)
        var blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' })
        var link = document.createElement('a')
        link.download = 'fundflow_' + Date.now() + '.svg'
        link.href = URL.createObjectURL(blob); link.click()
        setTimeout(function() { URL.revokeObjectURL(link.href) }, 200)
      } catch(err) { console.error('SVG export error:', err) }
    }

    /* ═══════════════════ LIFECYCLE ═══════════════════ */
    onMounted(function() {
      nextTick(function() {
        initSVG()
        if (hasTransfersData.value) {
          renderGraph()
        }
      })
    })

    onBeforeUnmount(function() {
      if (simulation) {
        simulation.stop()
        simulation = null
      }
      stopAllParticles()
    })

    watch(hasTransfersData, function(v) {
      if (v) {
        nextTick(function() {
          if (!svg) initSVG()
          renderGraph()
          nextTick(function() { fitAll() })
        })
      }
    })

    return {
      store, showEmpty, isLoadingState, showError, hasTransfersData,
      containerRef, svgRef, layoutMode, zoomPercent,
      legendList, statsTotal, statsAddrs, statsTokens,
      zoomIn, zoomOut, resetView, fitAll, switchLayout,
      exportPNG, exportSVG
    }
  }
}
</script>

<style scoped>
.ffp{display:flex;flex-direction:column;background:#0d1117;border-radius:10px;overflow:hidden;border:1px solid #21262d}
.ffp-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid #21262d;background:#161b22}
.ffp-title{margin:0;font-size:13.5px;font-weight:750;color:#e6edf3;display:flex;align-items:center;gap:7px;letter-spacing:-0.02em;font-family:inherit}
.ffp-title-icon{width:19px;height:19px;color:#3b82f6}
.ffp-toolbar{display:flex;align-items:center;gap:3px}
.ffp-tbtn{display:inline-flex;align-items:center;gap:4px;padding:5px 9px;border:1px solid #30363d;border-radius:6px;background:#161b22;color:#8b949e;font-size:11.5px;font-weight:600;cursor:pointer;transition:all .15s ease;font-family:inherit;line-height:1}
.ffp-tbtn:hover{background:#21262d;border-color:#484f58;color:#e6edf3}
.ffp-tbtn:active{transform:scale(.97)}
.ffp-tbtn-active{background:#21262d;border-color:#3b82f6;color:#3b82f6}
.ffp-export-btn svg{flex-shrink:0}
.ffp-divider{width:1px;height:20px;background:#30363d;margin:0 4px}

.ffp-empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:56px 20px;gap:12px;color:#484f58;font-size:13px}
.ffp-empty-icon{width:48px;height:48px;opacity:.35}
.ffp-loading{display:flex;align-items:center;justify-content:center;gap:10px;padding:48px 20px;color:#6e7681;font-size:13px}
.ffp-spinner{width:22px;height:22px;border:2.5px solid #30363d;border-top-color:#3b82f6;border-radius:50%;animation:ffpSpin .7s linear infinite}
@keyframes ffpSpin{to{transform:rotate(360deg)}}
.ffp-error-state{display:flex;align-items:center;justify-content:center;gap:6px;padding:20px;color:#f85149;font-size:12px;background:#3d1017;margin:12px 16px;border-radius:6px;border:1px solid #67080c}

/* Canvas */
.ffp-canvas-wrap{position:relative;width:100%;height:600px;overflow:hidden;background:#0d1117;cursor:grab;user-select:none}
.ffp-canvas-wrap:active{cursor:grabbing}
.ffp-svg{width:100%;height:100%;display:block;background:#0d1117}

/* Grid */
.ffp-grid-layer{pointer-events:none}

/* Edges */
.ffp-edge-layer{pointer-events:none}
.ffp-edge-group{pointer-events:all}
.ffp-edge-group:hover .ffp-edge-base{
  cursor:pointer;
}
/* Base path — always visible with arrow, dims on hover of other edges */
.ffp-edge-base{
  stroke-opacity:.65;
  transition:stroke-opacity .25s ease, stroke-width .2s ease;
}
/* Glow overlay — hidden by default, shown on active/hover */
.ffp-edge-glow{
  opacity:0;
  transition:opacity .2s ease;
  pointer-events:none;
}

/* Particles */
.ffp-particle-group{pointer-events:none}

/* Nodes */
.ffp-node-group{transition:all .2s ease}
.ffp-node-group:active{cursor:grabbing!important}

/* Labels */
.ffp-label-layer{pointer-events:none}
.ffp-label-group{pointer-events:all;cursor:default;transition:opacity .2s ease}

/* Tooltip inside foreignObject */
:deep(.ffp-tooltip-text-d3){
  background:#1c2128;
  color:#e6edf3;
  padding:4px 10px;
  border-radius:6px;
  font-size:10.5px;
  font-family:'JetBrains Mono',monospace;
  white-space:nowrap;
  box-shadow:0 4px 12px rgba(0,0,0,.45);
  border:1px solid #30363d;
  display:inline-block;
}

/* Zoom indicator */
.ffp-zoom-indicator{position:absolute;bottom:10px;left:10px;background:rgba(22,27,34,.88);border:1px solid #30363d;padding:3px 9px;border-radius:5px;font-size:10.5px;color:#8b949e;font-weight:600;font-family:'SF Mono',monospace;pointer-events:none}

/* Legend */
.ffp-legend{display:flex;align-items:center;gap:14px;padding:8px 16px;border-top:1px solid #21262d;background:#161b22;flex-wrap:wrap}
.ffp-legend-item{display:flex;align-items:center;gap:5px;font-size:11px;color:#8b949e;font-weight:600}
.ffp-legend-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}

/* Stats bar */
.ffp-stats-bar{display:flex;align-items:center;gap:24px;padding:8px 16px;border-top:1px solid #21262d;background:#161b22}
.ffp-stat{display:flex;align-items:baseline;gap:5px}
.ffp-stat-label{font-size:10.5px;color:#484f58;text-transform:uppercase;letter-spacing:.5px;font-weight:700}
.ffp-stat-val{font-size:14px;color:#e6edf3;font-weight:800;font-family:'JetBrains Mono',monospace}
</style>

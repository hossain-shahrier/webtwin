'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { getSiteGraph } from '../lib/api';
import styles from '../app/ui.module.css';

export interface SiteGraphPayload {
  nodes: Array<{
    id: string;
    name: string;
    visit_count?: number;
    primary_entity?: string | null;
  }>;
  edges: Array<{
    from: string;
    to: string | null;
    href: string;
    visited: boolean;
    link_type?: string;
  }>;
  visited_edges?: Array<{
    from_screen_id: string;
    to_screen_id: string;
    trigger?: string;
  }>;
  stats?: {
    total_discovered?: number;
    total_internal?: number;
    total_visited_links?: number;
    coverage_pct?: number;
  };
}

type SiteGraphProps = {
  investigationId: string;
  refreshKey?: number;
};

function layoutNodes(screens: SiteGraphPayload['nodes']): Node[] {
  const columns = Math.max(3, Math.ceil(Math.sqrt(screens.length || 1)));
  return screens.map((screen, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    const size = 36 + Math.min(24, (screen.visit_count ?? 1) * 4);
    return {
      id: screen.id,
      position: { x: col * 220, y: row * 120 },
      data: {
        label: screen.name || screen.id,
      },
      style: {
        width: size + 40,
        minHeight: size,
        borderRadius: 8,
        border: '2px solid #334155',
        background: '#0f172a',
        color: '#e2e8f0',
        fontSize: 12,
        padding: 8,
      },
    };
  });
}

function buildEdges(payload: SiteGraphPayload): Edge[] {
  const edges: Edge[] = [];
  const seen = new Set<string>();

  for (const link of payload.edges) {
    if (!link.to) continue;
    const key = `${link.from}→${link.to}:${link.href}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({
      id: key,
      source: link.from,
      target: link.to,
      label: link.href.length > 28 ? `${link.href.slice(0, 26)}…` : link.href,
      animated: link.visited,
      style: {
        stroke: link.visited ? '#38bdf8' : '#64748b',
        strokeWidth: link.visited ? 2 : 1,
        strokeDasharray: link.visited ? undefined : '6 4',
      },
    });
  }

  for (const edge of payload.visited_edges ?? []) {
    const key = `visited:${edge.from_screen_id}→${edge.to_screen_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({
      id: key,
      source: edge.from_screen_id,
      target: edge.to_screen_id,
      animated: true,
      style: { stroke: '#22c55e', strokeWidth: 2 },
    });
  }

  return edges;
}

export function SiteGraph({ investigationId, refreshKey = 0 }: SiteGraphProps) {
  const [payload, setPayload] = useState<SiteGraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSiteGraph(investigationId)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load site graph');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [investigationId, refreshKey]);

  const nodes = useMemo(
    () => layoutNodes(payload?.nodes ?? []),
    [payload?.nodes],
  );
  const edges = useMemo(
    () => (payload ? buildEdges(payload) : []),
    [payload],
  );

  const onNodeClick = useCallback((_: MouseEvent, node: Node) => {
    setSelected(node.id);
  }, []);

  if (error && !payload) {
    return <p className={styles.empty}>{error}</p>;
  }

  if (!payload || payload.nodes.length === 0) {
    return (
      <p className={styles.empty}>
        No site graph yet — links appear as pages are observed.
      </p>
    );
  }

  const stats = payload.stats ?? {};
  const selectedNode = payload.nodes.find((node) => node.id === selected);
  const outbound = payload.edges.filter((edge) => edge.from === selected);

  return (
    <div className={styles.stack}>
      <div className={styles.row} style={{ gap: '1rem', flexWrap: 'wrap' }}>
        <span className={styles.hint}>
          {payload.nodes.length} screens · {payload.edges.length} discovered links ·{' '}
          {Math.round((stats.coverage_pct ?? 0) * 100)}% coverage
        </span>
        <span className={styles.hint}>
          solid = visited · dashed = unvisited
        </span>
      </div>
      <div
        style={{
          height: 420,
          border: '1px solid #334155',
          borderRadius: 8,
        }}
      >
        <ReactFlow
          key={`${nodes.length}-${edges.length}`}
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          fitView
          minZoom={0.2}
          maxZoom={1.5}
        >
          <MiniMap pannable zoomable />
          <Controls />
          <Background gap={16} />
        </ReactFlow>
      </div>
      {selectedNode && (
        <div className={styles.panel} style={{ padding: '0.75rem' }}>
          <h3 className={styles.panelTitle}>{selectedNode.name || selectedNode.id}</h3>
          <p className={styles.hint}>Visits: {selectedNode.visit_count ?? 0}</p>
          {outbound.length > 0 && (
            <>
              <p className={styles.fieldLabel}>Outbound links</p>
              <ul className={styles.list}>
                {outbound.slice(0, 12).map((link) => (
                  <li key={`${link.from}-${link.href}`} className={styles.mono}>
                    {link.visited ? '✓' : '○'} {link.href}
                    {link.to ? ` → ${link.to}` : ''}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

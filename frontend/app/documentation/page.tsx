"use client";

import React from "react";
import Link from "next/link";
import { BookOpen, ExternalLink } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { DOCUMENTATION_SECTIONS } from "@/lib/documentationContent";

export default function DocumentationPage() {
  return (
    <AppShell>
      <div className="max-w-3xl mx-auto p-8 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-purple-400" />
            Documentation
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Concise assignment/demo guide for RoxStar. Details live in the repo{" "}
            <code className="text-slate-500">docs/</code> folder.
          </p>
        </div>

        <nav
          aria-label="Documentation sections"
          className="glass-card rounded-2xl border border-slate-800 p-4"
        >
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
            On this page
          </p>
          <ul className="flex flex-wrap gap-2">
            {DOCUMENTATION_SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="text-[11px] px-2 py-1 rounded-md bg-slate-900 border border-slate-800 text-slate-300 hover:text-purple-300 hover:border-purple-700/50"
                >
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="space-y-6">
          {DOCUMENTATION_SECTIONS.map((section) => (
            <section
              key={section.id}
              id={section.id}
              data-doc-section={section.id}
              className="glass-card rounded-2xl border border-slate-800 p-5 space-y-3 scroll-mt-8"
            >
              <h2 className="text-sm font-semibold text-white">{section.title}</h2>
              {section.paragraphs.map((p) => (
                <p key={p.slice(0, 32)} className="text-sm text-slate-400 leading-relaxed">
                  {p}
                </p>
              ))}
              {section.links && section.links.length > 0 ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {section.links.map((link) =>
                    link.external ? (
                      <a
                        key={link.href}
                        href={link.href}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-purple-300 hover:text-purple-200"
                      >
                        {link.label}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      <Link
                        key={link.href}
                        href={link.href}
                        className="inline-flex items-center gap-1 text-xs text-purple-300 hover:text-purple-200"
                      >
                        {link.label} →
                      </Link>
                    )
                  )}
                </div>
              ) : null}
            </section>
          ))}
        </div>
      </div>
    </AppShell>
  );
}

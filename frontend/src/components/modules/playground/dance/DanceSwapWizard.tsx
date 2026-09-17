'use client';

import { useRef, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle, Bookmark, Check, Cpu, FolderOpen, ImagePlus, Loader2, RotateCcw, Shirt, Upload, Wand2,
} from 'lucide-react';
import { mediaUrl } from '@/lib/mediaPath';
import { toast } from '@/store/toastStore';
import AssetSourcePicker from '../AssetSourcePicker';
import { useDanceSwap, type StepResult } from './useDanceSwap';
import type { SheetStyle } from './prompts';

function describeSaveError(err: unknown): string {
  const anyErr = err as { response?: { data?: { detail?: string } }; message?: string };
  return anyErr?.response?.data?.detail || anyErr?.message || String(err);
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

function StepShell({
  index, title, hint, done, children,
}: {
  index: number; title: string; hint: string; done: boolean; children: ReactNode;
}) {
  return (
    <section className="glass-panel atelier-card rounded-[20px] px-6 py-5">
      <header className="mb-4 flex items-start gap-3">
        <span
          className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[0.75rem] font-semibold ${
            done ? 'bg-primary text-on-accent' : 'bg-surface-inset text-text-muted'
          }`}
        >
          {done ? <Check size={14} aria-hidden="true" /> : index}
        </span>
        <div className="flex flex-col gap-0.5">
          <h3 className="font-display text-[1.0625rem] font-semibold tracking-tight text-foreground">
            {title}
          </h3>
          <p className="font-mono text-[0.6875rem] leading-relaxed text-text-muted">{hint}</p>
        </div>
      </header>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

const ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png'];

function FilePick({
  label, accept, value, onPick, icon,
}: {
  label: string; accept: string; value: string | null;
  onPick: (f: File) => void; icon: ReactNode;
}) {
  const t = useTranslations('playground.dance');
  const ref = useRef<HTMLInputElement>(null);
  const isVideo = accept.startsWith('video');
  return (
    <div className="flex flex-col gap-2">
      <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
        {label}
      </span>
      <button
        type="button"
        onClick={() => ref.current?.click()}
        className="group relative flex min-h-[132px] items-center justify-center overflow-hidden rounded-[14px] border border-dashed border-border-subtle bg-surface-inset transition-colors hover:border-primary cursor-pointer"
      >
        {value ? (
          isVideo ? (
            <video src={mediaUrl(value)} className="max-h-[220px] w-full object-contain" muted playsInline controls />
          ) : (
            <img src={mediaUrl(value)} alt={label} className="max-h-[220px] w-full object-contain" />
          )
        ) : (
          <span className="flex flex-col items-center gap-2 text-text-muted">
            {icon}
            <span className="font-mono text-[0.6875rem]">{label}</span>
          </span>
        )}
      </button>
      <input
        ref={ref}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          if (!isVideo) {
            const ext = f.name.split('.').pop()?.toLowerCase();
            if (!ext || !ALLOWED_IMAGE_EXTENSIONS.includes(ext)) {
              toast.error(t('invalidImageFormat'));
              e.target.value = '';
              return;
            }
          }
          onPick(f);
          e.target.value = '';
        }}
      />
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-[12px] border border-danger/40 bg-danger/10 px-3 py-2.5">
      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-danger" aria-hidden="true" />
      <p className="font-mono text-[0.6875rem] leading-relaxed text-danger break-words">{message}</p>
    </div>
  );
}

function RunButton({
  onClick, disabled, running, label, runningLabel,
}: {
  onClick: () => void; disabled: boolean; running: boolean;
  label: string; runningLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || running}
      className="flex items-center justify-center gap-2 rounded-[12px] bg-primary px-4 py-2.5 font-mono text-[0.75rem] font-medium text-on-accent transition-opacity disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
    >
      {running ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Wand2 size={14} aria-hidden="true" />}
      {running ? runningLabel : label}
    </button>
  );
}

function SaveToLibrary({
  result, category, onSave, label,
}: {
  result: StepResult; category: string; label: string;
  onSave: (r: StepResult, c: string) => Promise<unknown>;
}) {
  const t = useTranslations('playground.dance');
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle');

  return (
    <button
      type="button"
      disabled={status !== 'idle'}
      onClick={() => {
        setStatus('saving');
        onSave(result, category)
          .then(() => {
            setStatus('saved');
            toast.success(t('saveSuccess'));
          })
          .catch((err) => {
            setStatus('idle');
            toast.error(t('saveFailed'), { body: describeSaveError(err) });
          });
      }}
      className="flex items-center gap-1.5 rounded-[10px] border border-glass-border bg-glass px-2.5 py-1.5 font-mono text-[0.625rem] text-text-muted transition-colors hover:text-foreground cursor-pointer disabled:cursor-not-allowed disabled:opacity-60"
    >
      {status === 'saving'
        ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
        : <Bookmark size={12} aria-hidden="true" />}
      {status === 'saved' ? t('saveSuccess') : label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Wizard
// ---------------------------------------------------------------------------

const SHEET_STYLES: SheetStyle[] = ['illustration', 'anime', 'photoreal'];
const RESOLUTIONS = ['480p', '720p', '1080p'];
const ASPECT_RATIOS = ['adaptive', '9:16', '16:9', '1:1', '3:4', '4:3'];
const DURATION_MIN = 4;
const DURATION_MAX = 30;

export default function DanceSwapWizard() {
  const t = useTranslations('playground.dance');
  const { state, patch, effectivePrompt, actions } = useDanceSwap();

  const cap = state.depthCapability;
  const depthInfo = state.depthJob?.info;
  const motionReady = state.depthState === 'done' || Boolean(state.danceVideoPath);

  const [showSheetPicker, setShowSheetPicker] = useState(false);
  const [showDanceVideoPicker, setShowDanceVideoPicker] = useState(false);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-6 py-6">
      {/* ---------------- step 1: character sheet ---------------- */}
      <StepShell index={1} title={t('step1.title')} hint={t('step1.hint')} done={state.sheetState === 'done'}>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => patch({ sheetSource: 'generate' })}
            className={`rounded-[12px] border px-3 py-2 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
              state.sheetSource === 'generate'
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border-subtle bg-surface-inset text-text-muted'
            }`}
          >
            {t('step1.sourceGenerate')}
          </button>
          <button
            type="button"
            onClick={() => patch({ sheetSource: 'upload' })}
            className={`rounded-[12px] border px-3 py-2 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
              state.sheetSource === 'upload'
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border-subtle bg-surface-inset text-text-muted'
            }`}
          >
            {t('step1.sourceUpload')}
          </button>
        </div>

        {state.sheetSource === 'generate' ? (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FilePick
                label={t('step1.portrait')}
                accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                value={state.portraitPath}
                onPick={(f) => void actions.uploadPortrait(f)}
                icon={<ImagePlus size={20} aria-hidden="true" />}
              />
              <FilePick
                label={t('step1.outfitRef')}
                accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                value={state.outfitRefPath}
                onPick={(f) => void actions.uploadOutfitRef(f)}
                icon={<Shirt size={20} aria-hidden="true" />}
              />
            </div>

            <label className="flex flex-col gap-1.5">
              <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
                {t('step1.outfitLabel')}
              </span>
              <input
                value={state.outfit}
                onChange={(e) => patch({ outfit: e.target.value })}
                placeholder={t('step1.outfitPlaceholder')}
                className="rounded-[12px] border border-border-subtle bg-surface-inset px-3 py-2.5 font-mono text-[0.75rem] text-foreground outline-none focus:border-primary"
              />
            </label>

            <div className="flex flex-col gap-1.5">
              <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
                {t('step1.styleLabel')}
              </span>
              <div className="flex flex-wrap gap-2">
                {SHEET_STYLES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => patch({ sheetStyle: s })}
                    className={`rounded-[10px] border px-3 py-1.5 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
                      state.sheetStyle === s
                        ? 'border-primary bg-primary/15 text-foreground'
                        : 'border-glass-border bg-glass text-text-muted hover:text-foreground'
                    }`}
                  >
                    {t(`step1.style.${s}`)}
                  </button>
                ))}
              </div>
              {state.sheetStyle === 'photoreal' && (
                <p className="font-mono text-[0.625rem] leading-relaxed text-warning">
                  {t('step1.photorealWarning')}
                </p>
              )}
            </div>

            <RunButton
              onClick={() => void actions.generateSheet()}
              disabled={!state.portraitPath}
              running={state.sheetState === 'running'}
              label={t('step1.run')}
              runningLabel={t('step1.running')}
            />

            {state.sheetError && <ErrorBox message={state.sheetError} />}

            {state.sheet && (
              <div className="flex flex-col gap-2">
                <img
                  src={mediaUrl(state.sheet.mediaPath)}
                  alt={t('step1.title')}
                  className="w-full rounded-[14px] border border-border-subtle"
                />
                <div className="flex items-center gap-2">
                  <SaveToLibrary
                    result={state.sheet}
                    category="character"
                    onSave={actions.saveToLibrary}
                    label={t('step1.saveAsCharacter')}
                  />
                  <button
                    type="button"
                    onClick={() => void actions.generateSheet()}
                    className="flex items-center gap-1.5 rounded-[10px] border border-glass-border bg-glass px-2.5 py-1.5 font-mono text-[0.625rem] text-text-muted transition-colors hover:text-foreground cursor-pointer"
                  >
                    <RotateCcw size={12} aria-hidden="true" />
                    {t('regenerate')}
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <p className="font-mono text-[0.625rem] leading-relaxed text-text-muted">
              {t('step1.sourceUploadHint')}
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <FilePick
                label={t('step1.sheetFile')}
                accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                value={state.sheet?.mediaPath ?? null}
                onPick={(f) => void actions.uploadSheet(f)}
                icon={<ImagePlus size={20} aria-hidden="true" />}
              />
              <button
                type="button"
                onClick={() => setShowSheetPicker(true)}
                className="flex flex-col items-center justify-center gap-1.5 rounded-[14px] border border-dashed border-border-subtle bg-surface-inset px-4 py-6 font-mono text-[0.6875rem] text-text-muted transition-colors hover:border-primary hover:text-foreground cursor-pointer"
              >
                <FolderOpen size={20} aria-hidden="true" />
                {t('pickFromLibrary')}
              </button>
            </div>
            <AssetSourcePicker
              isOpen={showSheetPicker}
              onClose={() => setShowSheetPicker(false)}
              onSelect={(path) => {
                actions.pickSheet(path);
                setShowSheetPicker(false);
              }}
              accept="image"
            />
            {state.sheet && (
              <div className="flex flex-col gap-2">
                <img
                  src={mediaUrl(state.sheet.mediaPath)}
                  alt={t('step1.title')}
                  className="w-full rounded-[14px] border border-border-subtle"
                />
                <SaveToLibrary
                  result={state.sheet}
                  category="character"
                  onSave={actions.saveToLibrary}
                  label={t('step1.saveAsCharacter')}
                />
              </div>
            )}
          </>
        )}
      </StepShell>

      {/* ---------------- step 2: motion reference ---------------- */}
      <StepShell index={2} title={t('step2.title')} hint={t('step2.hint')} done={motionReady}>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => patch({ motionSource: 'extract' })}
            className={`rounded-[12px] border px-3 py-2 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
              state.motionSource === 'extract'
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border-subtle bg-surface-inset text-text-muted'
            }`}
          >
            {t('step2.sourceExtract')}
          </button>
          <button
            type="button"
            onClick={() => patch({ motionSource: 'upload' })}
            className={`rounded-[12px] border px-3 py-2 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
              state.motionSource === 'upload'
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border-subtle bg-surface-inset text-text-muted'
            }`}
          >
            {t('step2.sourceUpload')}
          </button>
        </div>

        {state.motionSource === 'extract' ? (
          <>
            {cap && (
              <div className="flex items-start gap-2 rounded-[12px] border border-glass-border bg-glass px-3 py-2.5">
                <Cpu size={14} className="mt-0.5 shrink-0 text-text-muted" aria-hidden="true" />
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono text-[0.6875rem] text-foreground">
                    {cap.available === false
                      ? t('step2.noGpuOnServer')
                      : cap.device === 'cuda'
                        ? t('step2.gpu', { name: cap.gpu_name ?? '', vram: cap.vram_gb ?? 0 })
                        : t('step2.cpu')}
                  </span>
                  {cap.device === 'cuda' && (
                    <span className="font-mono text-[0.625rem] text-text-muted">
                      {t('step2.plan', {
                        encoder: cap.recommended_encoder ?? '',
                        size: cap.recommended_input_size ?? 0,
                      })}
                    </span>
                  )}
                  {cap.warning && (
                    <span className="font-mono text-[0.625rem] text-warning">{cap.warning}</span>
                  )}
                </div>
              </div>
            )}

            <FilePick
              label={t('step2.danceVideo')}
              accept="video/*"
              value={state.danceVideoPath}
              onPick={(f) => void actions.uploadDanceVideo(f)}
              icon={<Upload size={20} aria-hidden="true" />}
            />

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
                  {t('step2.maxSeconds')}
                </span>
                <input
                  type="number"
                  min={1}
                  value={state.maxSeconds ?? ''}
                  placeholder={t('step2.wholeClip')}
                  onChange={(e) => patch({ maxSeconds: e.target.value ? Number(e.target.value) : null })}
                  className="rounded-[12px] border border-border-subtle bg-surface-inset px-3 py-2 font-mono text-[0.75rem] text-foreground outline-none focus:border-primary"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
                  {t('step2.targetFps')}
                </span>
                <input
                  type="number"
                  min={1}
                  value={state.targetFps ?? ''}
                  placeholder={t('step2.sourceFps')}
                  onChange={(e) => patch({ targetFps: e.target.value ? Number(e.target.value) : null })}
                  className="rounded-[12px] border border-border-subtle bg-surface-inset px-3 py-2 font-mono text-[0.75rem] text-foreground outline-none focus:border-primary"
                />
              </label>
            </div>
            <p className="font-mono text-[0.625rem] leading-relaxed text-text-muted">
              {t('step2.fpsHint')}
            </p>

            <RunButton
              onClick={() => void actions.generateDepth()}
              disabled={!state.danceVideoPath || cap?.available === false}
              running={state.depthState === 'running'}
              label={t('step2.run')}
              runningLabel={state.depthJob?.message || t('step2.running')}
            />

            {state.depthState === 'running' && state.depthJob && (
              <div className="h-1 overflow-hidden rounded-full bg-surface-inset">
                <div
                  className="h-full bg-primary transition-[width]"
                  style={{ width: `${Math.round((state.depthJob.progress || 0) * 100)}%` }}
                />
              </div>
            )}

            {state.depthError && <ErrorBox message={state.depthError} />}

            {state.depthState === 'done' && state.depthJob?.output_path && (
              <div className="flex flex-col gap-2">
                <video
                  src={mediaUrl(state.depthJob.output_path)}
                  className="w-full rounded-[14px] border border-border-subtle"
                  controls
                  muted
                  playsInline
                />
                {depthInfo && (
                  <p className="font-mono text-[0.625rem] text-text-muted">
                    {t('step2.stats', {
                      frames: depthInfo.frames ?? 0,
                      seconds: depthInfo.elapsed_sec ?? 0,
                      encoder: depthInfo.encoder ?? '',
                      size: depthInfo.input_size ?? 0,
                      vram: depthInfo.peak_vram_gb ?? 0,
                    })}
                  </p>
                )}
              </div>
            )}
          </>
        ) : (
          <>
            <p className="font-mono text-[0.625rem] leading-relaxed text-text-muted">
              {t('step2.sourceUploadHint')}
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <FilePick
                label={t('step2.depthVideo')}
                accept="video/*"
                value={state.danceVideoPath}
                onPick={(f) => void actions.uploadDanceVideo(f)}
                icon={<Upload size={20} aria-hidden="true" />}
              />
              <button
                type="button"
                onClick={() => setShowDanceVideoPicker(true)}
                className="flex flex-col items-center justify-center gap-1.5 rounded-[14px] border border-dashed border-border-subtle bg-surface-inset px-4 py-6 font-mono text-[0.6875rem] text-text-muted transition-colors hover:border-primary hover:text-foreground cursor-pointer"
              >
                <FolderOpen size={20} aria-hidden="true" />
                {t('pickFromLibrary')}
              </button>
            </div>
            <AssetSourcePicker
              isOpen={showDanceVideoPicker}
              onClose={() => setShowDanceVideoPicker(false)}
              onSelect={(path) => {
                actions.pickDanceVideo(path);
                setShowDanceVideoPicker(false);
              }}
              accept="video"
            />
            {state.danceVideoPath && (
              <video
                src={mediaUrl(state.danceVideoPath)}
                className="w-full rounded-[14px] border border-border-subtle"
                controls
                muted
                playsInline
              />
            )}
          </>
        )}
      </StepShell>

      {/* ---------------- step 3: compose ---------------- */}
      <StepShell index={3} title={t('step3.title')} hint={t('step3.hint')} done={state.composeState === 'done'}>
        <label className={`flex items-center gap-2 ${!state.sheet ? 'opacity-40' : ''}`}>
          <input
            type="checkbox"
            checked={state.useSheet && Boolean(state.sheet)}
            disabled={!state.sheet}
            onChange={(e) => patch({ useSheet: e.target.checked })}
            className="h-3.5 w-3.5 accent-[var(--color-primary)]"
          />
          <span className="font-mono text-[0.6875rem] text-foreground">{t('step3.useSheet')}</span>
        </label>
        <p className="font-mono text-[0.625rem] leading-relaxed text-text-muted">
          {!state.sheet
            ? t('step3.noSheet')
            : state.useSheet
              ? t('step3.useSheetOn')
              : t('step3.useSheetOff')}
        </p>

        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
            {t('step3.scene')}
          </span>
          <input
            value={state.scene}
            onChange={(e) => patch({ scene: e.target.value })}
            placeholder={t('step3.scenePlaceholder')}
            className="rounded-[12px] border border-border-subtle bg-surface-inset px-3 py-2.5 font-mono text-[0.75rem] text-foreground outline-none focus:border-primary"
          />
        </label>

        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
            {t('step3.resolution')}
          </span>
          <div className="flex gap-2">
            {RESOLUTIONS.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => patch({ resolution: r })}
                className={`rounded-[10px] border px-3 py-1.5 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
                  state.resolution === r
                    ? 'border-primary bg-primary/15 text-foreground'
                    : 'border-glass-border bg-glass text-text-muted hover:text-foreground'
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
            {t('step3.aspectRatio')}
          </span>
          <div className="flex flex-wrap gap-2">
            {ASPECT_RATIOS.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => patch({ aspectRatio: r })}
                className={`rounded-[10px] border px-3 py-1.5 font-mono text-[0.6875rem] transition-colors cursor-pointer ${
                  state.aspectRatio === r
                    ? 'border-primary bg-primary/15 text-foreground'
                    : 'border-glass-border bg-glass text-text-muted hover:text-foreground'
                }`}
              >
                {r === 'adaptive' ? t('step3.aspectRatioAdaptive') : r}
              </button>
            ))}
          </div>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
            {t('step3.duration')}
          </span>
          <input
            type="number"
            min={DURATION_MIN}
            max={DURATION_MAX}
            value={state.duration ?? ''}
            placeholder={t('step3.durationFollowClip')}
            onChange={(e) =>
              patch({ duration: e.target.value ? Number(e.target.value) : null })
            }
            className="rounded-[12px] border border-border-subtle bg-surface-inset px-3 py-2 font-mono text-[0.75rem] text-foreground outline-none focus:border-primary"
          />
          <p className="font-mono text-[0.625rem] leading-relaxed text-text-muted">
            {t('step3.durationHint', { min: DURATION_MIN, max: DURATION_MAX })}
          </p>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
            {t('step3.prompt')}
          </span>
          <textarea
            value={effectivePrompt}
            onChange={(e) => patch({ composePrompt: e.target.value, composePromptDirty: true })}
            rows={5}
            className="resize-y rounded-[12px] border border-border-subtle bg-surface-inset px-3 py-2.5 font-mono text-[0.6875rem] leading-relaxed text-foreground outline-none focus:border-primary"
          />
          {state.composePromptDirty && (
            <button
              type="button"
              onClick={() => patch({ composePromptDirty: false, composePrompt: '' })}
              className="self-start font-mono text-[0.625rem] text-text-muted underline hover:text-foreground cursor-pointer"
            >
              {t('step3.resetPrompt')}
            </button>
          )}
        </label>

        <RunButton
          onClick={() => void actions.compose()}
          disabled={!motionReady}
          running={state.composeState === 'running'}
          label={t('step3.run')}
          runningLabel={t('step3.running')}
        />

        {state.composeError && <ErrorBox message={state.composeError} />}

        {state.composed && (
          <div className="flex flex-col gap-2">
            <video
              src={mediaUrl(state.composed.mediaPath)}
              className="w-full rounded-[14px] border border-border-subtle"
              controls
              playsInline
            />
            <SaveToLibrary
              result={state.composed}
              category="general"
              onSave={actions.saveToLibrary}
              label={t('step3.saveToLibrary')}
            />
          </div>
        )}
      </StepShell>
    </div>
  );
}

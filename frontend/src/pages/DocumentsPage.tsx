import { useReducer, useRef } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { m } from 'framer-motion'
import { Upload, FileText, Archive, Search } from 'lucide-react'
import { useDocuments, useUploadDocument, useArchiveDocument } from '../hooks/useDocuments'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { Badge } from '../components/ui/Badge'
import { formatDate } from '../utils/date'
import { apiErrorDetail } from '../utils/apiError'
import { DOCUMENT_TYPE_OPTIONS, documentTypeLabel } from '../utils/documentTypes'
import type { DocumentType } from '../types'

type UploadForm = {
  document_type: DocumentType
  title: string
}

type DocumentsState = {
  search: string
  typeFilter: DocumentType | undefined
  showUpload: boolean
  uploadForm: UploadForm
  selectedFile: File | null
}

type DocumentsAction =
  | { type: 'SET_SEARCH'; payload: string }
  | { type: 'SET_TYPE_FILTER'; payload: DocumentType | undefined }
  | { type: 'OPEN_UPLOAD' }
  | { type: 'CLOSE_UPLOAD' }
  | { type: 'SELECT_FILE'; payload: File }
  | { type: 'SET_UPLOAD_TITLE'; payload: string }
  | { type: 'SET_UPLOAD_TYPE'; payload: DocumentType }
  | { type: 'RESET_AFTER_UPLOAD' }

const INITIAL_UPLOAD_FORM: UploadForm = { document_type: 'deposit_policy', title: '' }

const initialDocumentsState: DocumentsState = {
  search: '',
  typeFilter: undefined,
  showUpload: false,
  uploadForm: INITIAL_UPLOAD_FORM,
  selectedFile: null,
}

function documentsReducer(state: DocumentsState, action: DocumentsAction): DocumentsState {
  switch (action.type) {
    case 'SET_SEARCH':
      return { ...state, search: action.payload }
    case 'SET_TYPE_FILTER':
      return { ...state, typeFilter: action.payload }
    case 'OPEN_UPLOAD':
      return { ...state, showUpload: true }
    case 'CLOSE_UPLOAD':
      return { ...state, showUpload: false, uploadForm: INITIAL_UPLOAD_FORM, selectedFile: null }
    case 'SELECT_FILE':
      return {
        ...state,
        selectedFile: action.payload,
        uploadForm: state.uploadForm.title
          ? state.uploadForm
          : { ...state.uploadForm, title: action.payload.name.replace(/\.[^/.]+$/, '') },
      }
    case 'SET_UPLOAD_TITLE':
      return { ...state, uploadForm: { ...state.uploadForm, title: action.payload } }
    case 'SET_UPLOAD_TYPE':
      return { ...state, uploadForm: { ...state.uploadForm, document_type: action.payload } }
    case 'RESET_AFTER_UPLOAD':
      return { ...state, showUpload: false, uploadForm: INITIAL_UPLOAD_FORM, selectedFile: null }
    default:
      return state
  }
}

export function DocumentsPage() {
  const [state, dispatch] = useReducer(documentsReducer, initialDocumentsState)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { search, typeFilter, showUpload, uploadForm, selectedFile } = state

  const docs = useDocuments({ search: search || undefined, document_type: typeFilter, status: 'active' })
  const uploadDoc = useUploadDocument()
  const archiveDoc = useArchiveDocument()
  const uploadError = apiErrorDetail(uploadDoc.error)
  const canUpload = Boolean(selectedFile && uploadForm.title.trim() && uploadForm.document_type && !uploadDoc.isPending)

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      dispatch({ type: 'SELECT_FILE', payload: file })
    }
  }

  const handleUpload = (e: FormEvent) => {
    e.preventDefault()
    if (!selectedFile || !uploadForm.title.trim()) return
    uploadDoc.mutate(
      { file: selectedFile, document_type: uploadForm.document_type, title: uploadForm.title.trim() },
      { onSuccess: () => dispatch({ type: 'RESET_AFTER_UPLOAD' }) },
    )
  }

  const openUpload = () => {
    uploadDoc.reset()
    dispatch({ type: 'OPEN_UPLOAD' })
  }

  const closeUpload = () => {
    uploadDoc.reset()
    dispatch({ type: 'CLOSE_UPLOAD' })
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-medium text-text-primary">Documents</h1>
          <p className="text-sm text-text-muted mt-0.5">Policies, contracts, FAQs, and other internal knowledge</p>
        </div>
        <button type="button" onClick={openUpload} className="btn-primary gap-1.5">
          <Upload className="w-4 h-4" />
          Upload document
        </button>
      </div>

      {/* Upload modal */}
      {showUpload && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget && !uploadDoc.isPending) closeUpload() }}
        >
          <m.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-surface rounded-xl border border-border shadow-modal p-6 w-full max-w-md"
          >
            <h2 className="text-base font-semibold text-text-primary mb-4">Upload document</h2>
            <p className="text-xs text-text-muted mb-4">Only plain text (.txt) files are supported. UTF-8 encoding required.</p>
            <form onSubmit={handleUpload} className="space-y-3">
              {/* File drop area */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadDoc.isPending}
                className="w-full border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-accent/50 hover:bg-accent-soft/30 transition-colors"
              >
                <Upload className="w-8 h-8 text-text-muted mx-auto mb-2" />
                {selectedFile ? (
                  <p className="text-sm font-medium text-text-primary">{selectedFile.name}</p>
                ) : (
                  <p className="text-sm text-text-muted">Click to select a .txt file</p>
                )}
              </button>
              <input ref={fileInputRef} type="file" accept=".txt" onChange={handleFileChange} aria-label="Upload a .txt document file" className="hidden" />

              <div>
                <label htmlFor="doc-title" className="block text-xs font-medium text-text-primary mb-1.5">Title</label>
                <input
                  id="doc-title"
                  type="text"
                  value={uploadForm.title}
                  onChange={(e) => dispatch({ type: 'SET_UPLOAD_TITLE', payload: e.target.value })}
                  disabled={uploadDoc.isPending}
                  placeholder="Document title"
                  className="input-base"
                />
              </div>
              <div>
                <label htmlFor="doc-type" className="block text-xs font-medium text-text-primary mb-1.5">Document type</label>
                <select
                  id="doc-type"
                  value={uploadForm.document_type}
                  onChange={(e) => dispatch({ type: 'SET_UPLOAD_TYPE', payload: e.target.value as DocumentType })}
                  disabled={uploadDoc.isPending}
                  className="input-base"
                >
                  {DOCUMENT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>
              {uploadError && (
                <div className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-danger" role="alert">
                  Upload failed: {uploadError}
                </div>
              )}
              <div className="flex gap-2 pt-1">
                <button type="submit" disabled={!canUpload} className="btn-primary flex-1 disabled:opacity-60">
                  {uploadDoc.isPending ? 'Uploading…' : 'Upload'}
                </button>
                <button type="button" onClick={closeUpload} disabled={uploadDoc.isPending} className="btn-secondary disabled:opacity-60">Cancel</button>
              </div>
            </form>
          </m.div>
        </m.div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search documents…"
            aria-label="Search documents"
            value={search}
            onChange={(e) => dispatch({ type: 'SET_SEARCH', payload: e.target.value })}
            className="input-base pl-9"
          />
        </div>
        <select
          value={typeFilter ?? ''}
          onChange={(e) => dispatch({ type: 'SET_TYPE_FILTER', payload: (e.target.value || undefined) as DocumentType | undefined })}
          aria-label="Filter by document type"
          className="input-base w-auto"
        >
          <option value="">All types</option>
          {DOCUMENT_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      {docs.isLoading ? (
        <PageLoader />
      ) : docs.isError ? (
        <ErrorState onRetry={docs.refetch} />
      ) : !docs.data?.length ? (
        <EmptyState
          title="No documents"
          description="Upload contracts, FAQs, and pricing sheets to power AI replies."
          icon={<FileText className="w-6 h-6" />}
          action={<button type="button" onClick={openUpload} className="btn-primary">Upload first document</button>}
        />
      ) : (
        <div className="grid gap-3">
          {docs.data.map((doc, i) => (
            <m.div
              key={doc.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.04 }}
              className="card p-4 flex items-center gap-4 hover:shadow-card-hover transition-shadow"
            >
              <div className="w-10 h-10 rounded-lg bg-info-soft border border-info/20 flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5 text-info" strokeWidth={1.75} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">{doc.title}</p>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant="info">{documentTypeLabel(doc.document_type)}</Badge>
                  <Badge variant="neutral">{doc.status}</Badge>
                  {doc.original_filename && <span className="text-[11px] text-text-muted truncate">{doc.original_filename}</span>}
                  <span className="text-[11px] text-text-muted">Updated {formatDate(doc.updated_at)}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => archiveDoc.mutate(doc.id)}
                className="flex items-center gap-1.5 text-xs text-text-muted hover:text-danger transition-colors p-2"
                aria-label="Archive document"
                title="Archive"
              >
                <Archive className="w-4 h-4" />
              </button>
            </m.div>
          ))}
        </div>
      )}
    </div>
  )
}

package server

import (
	"context"
	"sync"

	"github.com/wandb/wandb/nexus/internal/shared"
	"github.com/wandb/wandb/nexus/pkg/observability"
	"github.com/wandb/wandb/nexus/pkg/service"
)

// Stream is a collection of components that work together to handle incoming
// data for a W&B run, store it locally, and send it to a W&B server.
// Stream.handler receives incoming data from the client and dispatches it to
// Stream.writer, which writes it to a local file. Stream.writer then sends the
// data to Stream.sender, which sends it to the W&B server. Stream.dispatcher
// handles dispatching responses to the appropriate client responders.
type Stream struct {
	// ctx is the context for the stream
	ctx context.Context

	// wg is the WaitGroup for the stream
	wg sync.WaitGroup

	// handler is the handler for the stream
	handler *Handler

	// dispatcher is the dispatcher for the stream
	dispatcher *Dispatcher

	// writer is the writer for the stream
	writer *Writer

	// sender is the sender for the stream
	sender *Sender

	// settings is the settings for the stream
	settings *service.Settings

	// logger is the logger for the stream
	logger *observability.NexusLogger

	// inChan is the channel for incoming messages
	inChan chan *service.Record
}

// NewStream creates a new stream with the given settings and responders.
func NewStream(ctx context.Context, settings *service.Settings, streamId string) *Stream {
	logFile := settings.GetLogInternal().GetValue()
	logger := SetupStreamLogger(logFile, settings)

	stream := &Stream{
		ctx:      ctx,
		wg:       sync.WaitGroup{},
		settings: settings,
		logger:   logger,
		inChan:   make(chan *service.Record, BufferSize),
	}
	stream.Start()
	return stream
}

// AddResponders adds the given responders to the stream's dispatcher.
func (s *Stream) AddResponders(entries ...ResponderEntry) {
	s.dispatcher.AddResponders(entries...)
}

// Start starts the stream's handler, writer, sender, and dispatcher.
// We use Stream's wait group to ensure that all of these components are cleanly
// finalized and closed when the stream is closed in Stream.Close().
func (s *Stream) Start() {
	s.logger.Info("created new stream", "id", s.settings.RunId)

	s.handler = NewHandler(s.ctx, s.settings, s.logger)
	s.writer = NewWriter(s.ctx, s.settings, s.logger)
	s.sender = NewSender(s.ctx, s.settings, s.logger)
	s.dispatcher = NewDispatcher(s.logger)

	// handle the client requests
	s.wg.Add(1)
	go func() {
		s.handler.do(s.inChan, s.sender.loopbackChan)
		s.wg.Done()
	}()

	// write the data to a transaction log
	s.wg.Add(1)
	go func() {
		s.writer.do(s.handler.fwdChan)
		s.wg.Done()
	}()

	// send the data to the server
	s.wg.Add(1)
	go func() {
		s.sender.do(s.writer.fwdChan)
		s.wg.Done()
	}()

	// handle dispatching between components
	s.wg.Add(1)
	go func() {
		s.dispatcher.do(s.handler.outChan, s.sender.outChan)
		s.wg.Done()
	}()

	s.logger.Debug("starting stream", "id", s.settings.RunId)
}

// HandleRecord handles the given record by sending it to the stream's handler.
func (s *Stream) HandleRecord(rec *service.Record) {
	s.logger.Debug("handling record", "record", rec)
	s.inChan <- rec
}

func (s *Stream) GetRun() *service.RunRecord {
	return s.handler.GetRun()
}

// Close closes the stream's handler, writer, sender, and dispatcher.
// This can be triggered by the client (force=False) or by the server (force=True).
// We need the ExitRecord to initiate the shutdown procedure (which we
// either get from the client, or generate ourselves if the server is shutting us down).
// This will trigger the defer state machines (SM) in the stream's components:
//   - when the sender's SM gets to the final state, it will Close the handler
//   - this will trigger the handler to Close the writer
//   - this will trigger the writer to Close the sender
//
// This will finish the Stream's wait group, which will allow the stream to be
// garbage collected.
func (s *Stream) Close() {
	// Close and wait for input channel to shutdown
	close(s.inChan)
	s.wg.Wait()
}

func (s *Stream) FinishAndClose(exitCode int32) {
	// send exit record to handler
	record := &service.Record{
		RecordType: &service.Record_Exit{
			Exit: &service.RunExitRecord{
				ExitCode: exitCode,
			}},
		Control: &service.Control{AlwaysSend: true},
	}
	s.HandleRecord(record)

	s.Close()

	s.PrintFooter()
	s.logger.Info("closed stream", "id", s.settings.RunId)
}

func (s *Stream) PrintFooter() {
	run := s.GetRun()
	shared.PrintHeadFoot(run, s.settings)
}
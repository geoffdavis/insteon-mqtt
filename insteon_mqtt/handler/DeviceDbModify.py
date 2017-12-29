#===========================================================================
#
# Device all link database modification handler.
#
#===========================================================================
from .. import log
from .. import message as Msg
from .Base import Base

LOG = log.get_logger()


class DeviceDbModify(Base):
    """Device all link database modification handler.

    This handles message that arrive from adding, changing, or deleting
    records in the device's all link database.  It will make the necessary
    modifications to the device's all link database class to reflect what
    happened on the physical device.

    In many cases, a series of commands must be sent to the device to change
    the database. So the handler can be passed future commands to send using
    add_update().  When a command is finished, the next command in the queue
    will be sent.  If any command fails, the sequence stops.
    """
    def __init__(self, device_db, entry, on_done):
        """Constructor

        Args:
          device_db:       (db.Device) The device database being changed.
          entry:           (db.DeviceEntry) The new record or record being
                           erased.  This is the entry that the db will have
                           if the command works.
          on_done:         Finished callback.  This is called once for each
                           call added to the handler.  Signature is:
                              on_done(success, msg, entry)
        """
        super().__init__(on_done)

        self.db = device_db

        # The entry being modified.  Also store the first entry - that's the
        # one we'll pass to the on_done callback.  In theory on_done maybe?
        # should be called with each call but the add_update() code is only
        # used by db/Device.py to add an update after an addition so we want
        # the first call entry passed to teh callback so that the remote
        # updating system in device/Base.py works properly.
        self.entry = entry
        self.orig_entry = entry

        # Tuple of (msg, entry) to send next.  If the first calls ACK's,
        # we'll update self.entry and send the next msg and continue until
        # this is empty.
        self.next = []

    #-----------------------------------------------------------------------
    def add_update(self, msg, entry):
        """Add a future call.

        The input message and entry will be sent after the current
        transaction completes successfully.

        Args:
          msg:    The next message to send.
          entry:  (db.DeviceEntry) The new record or record being
                  erased.  This is the entry that the db will have
                  if the command works.
        """
        self.next.append((msg, entry))

    #-----------------------------------------------------------------------
    def msg_received(self, protocol, msg):
        """See if we can handle the message.

        This will update the modem's database if the command works.  Then the
        next message is written out.

        Args:
          protocol:  (Protocol) The Insteon Protocol object
          msg:       Insteon message object that was read.

        Returns:
          Msg.UNKNOWN if we can't handle this message.
          Msg.CONTINUE if we handled the message and expect more.
          Msg.FINISHED if we handled the message and are done.
        """
        if isinstance(msg, Msg.OutExtended):
            # See if the message address matches our expected reply.
            if msg.to_addr == self.db.addr and msg.cmd1 == 0x2f:
                # ACK - command is ok - wait for ACK from device.
                if msg.is_ack:
                    return Msg.CONTINUE

                # NAK - device rejected command.
                else:
                    LOG.error("Device NAK of device db modify: %s", msg)
                    self.on_done(False, "Device database update failed", None)
                    return Msg.FINISHED

        elif isinstance(msg, Msg.InpStandard):
            # See if the message address matches our expected reply.
            if msg.from_addr == self.db.addr and msg.cmd1 == 0x2f:
                # ACK or NAK - either way this transaction is complete.
                if msg.flags.type == Msg.Flags.Type.DIRECT_ACK:
                    # Entry could be new entry, and update to an existing
                    # entry, or an marked unused (deletion).
                    LOG.info("Updating entry: %s", self.entry)
                    self.db.add_entry(self.entry)

                    # Send the next database update message.
                    if self.next:
                        LOG.info("%s sending next db update", self.db.addr)
                        msg, self.entry = self.next.pop(0)
                        protocol.send(msg, self)

                    # Only run the done callback if this is the last message
                    # in the chain.
                    else:
                        self.on_done(True, "Device database update complete",
                                     self.orig_entry)

                elif msg.flags.type == Msg.Flags.Type.DIRECT_NAK:
                    LOG.error("%s db mod NAK: %s", self.db.addr, msg)
                    self.on_done(False, "Device database update failed", None)

                else:
                    LOG.error("%s db mod unexpected msg type: %s",
                              self.db.addr, msg)
                    self.on_done(False, "Device database update failed", None)

                return Msg.FINISHED

        return Msg.UNKNOWN

    #-----------------------------------------------------------------------

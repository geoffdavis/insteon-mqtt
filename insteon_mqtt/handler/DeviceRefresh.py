#===========================================================================
#
# Device refresh (ping) command handler.
#
#===========================================================================
from .. import log
from .. import message as Msg
from .Base import Base
from .DeviceDbGet import DeviceDbGet

LOG = log.get_logger()


class DeviceRefresh(Base):
    """Refresh the state and database version of a device handler.

    This handles device refresh messages.  Some devices don't respond
    very well (look at you SmokeBridge) so the handler has a built in
    retry system to resend the initial message if the handler times
    out.

    When a response arrives, device.handle_refresh(msg) is called to
    extract the current state of the device (on/off, dimmer level,
    etc).  Additionally, we'll check the device's database delta
    version to see if the database needs to re-downloaded from the
    device.  If it does, the handler will send a new message to
    request that.
    """
    def __init__(self, device, msg, force, num_retry=3):
        """Constructor

        Args
          device:    (Device) The Insteon device.
          msg:       (message) The refresh message being sent.  This will
                     be sent again if we time out.
          force:     (bool) If True, force a db download.  If False, only
                     download the db if it's out of date.
          num_retry: (int) The number of retries to attempt on the refresh
                     message before giving up.
        """
        super().__init__()

        self.device = device
        self.addr = device.addr
        self.msg = msg
        self.force = force
        self.send_count = 1
        self.num_retry = num_retry

    #-----------------------------------------------------------------------
    def is_expired(self, protocol, t):
        """See if the time out time has been exceeded.

        Args:
          protocol:  (Protocol) The Insteon Protocol object.
          t:         (float) Current time tag as a Unix clock time.

        Returns:
          Returns True if the message has timed out or False otherwise.
        """
        # If we haven't expired, return.
        if not super().is_expired(protocol, t):
            return False

        LOG.warning("Device %s refresh timed out with try %s of %s", self.addr,
                    self.send_count, self.num_retry)

        # Some devices like the smoke bridge have issues and don't
        # seem to respond very well.  So we'll retry a few times to
        # send the refresh command.
        if self.send_count < self.num_retry:
            self.send_count += 1

            # Resend the refresh command.
            protocol.send(self.msg, self)

        # Tell the protocol that we're expired.  This will end this
        # handler and send the next message which at some point will
        # be our retry command with ourselves as the handler again.
        return True

    #-----------------------------------------------------------------------
    def msg_received(self, protocol, msg):
        """See if we can handle the message.

        Args:
          protocol:  (Protocol) The Insteon Protocol object
          msg:       Insteon message object that was read.

        Returns:
          Msg.UNKNOWN if we can't handle this message.
          Msg.CONTINUE if we handled the message and expect more.
          Msg.FINISHED if we handled the message and are done.
        """
        # Probably an echo back of our sent message.
        if isinstance(msg, Msg.OutStandard) and msg.to_addr == self.addr:
            if msg.is_ack:
                LOG.debug("%s ACK response", self.addr)
                return Msg.CONTINUE
            else:
                LOG.error("%s NAK response", self.addr)
                return Msg.FINISHED

        # See if this is the standard message ack/nak we're expecting.
        elif isinstance(msg, Msg.InpStandard) and msg.from_addr == self.addr:
            # Since we got the message we expected, turn off retries.
            self.send_count = self.num_retry

            # Call the device refresh handler.  This sets the current
            # device state which is usually stored in cmd2.
            self.device.handle_refresh(msg)

            # All link database delta is stored in cmd1 so we if we have
            # the latest version.  If not, schedule an update.
            if not self.force and self.device.db.is_current(msg.cmd1):
                LOG.info("Device database is current at delta %s", msg.cmd1)

            else:
                LOG.info("Device %s db out of date - refreshing", self.addr)

                # Clear the current database values.
                self.device.db.clear()

                # When the update message below ends, update the db
                # delta w/ the current value and save the database.
                def on_done(success, message):
                    if success:
                        LOG.info("%s database download complete\n%s",
                                 self.addr, self.device.db)
                        self.device.db.set_delta(msg.cmd1)

                # Request that the device send us all of it's database
                # records.  These will be streamed as fast as possible
                # to us and the handler will update the database
                db_msg = Msg.OutExtended.direct(self.addr, 0x2f, 0x00,
                                                bytes(14))
                msg_handler = DeviceDbGet(self.device.db, on_done,
                                          msg=db_msg)  # TODO: fix this
                protocol.send(db_msg, msg_handler)

            # Either way - this transaction is complete.
            return Msg.FINISHED

        # Unknown message - not for us.
        return Msg.UNKNOWN

    #-----------------------------------------------------------------------

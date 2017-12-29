#===========================================================================
#
# Insteon broadcast message handler
#
#===========================================================================
from .. import log
from .. import message as Msg
from .Base import Base

LOG = log.get_logger()


class StandardCmd(Base):
    """Insteon standard input mesage handler.

    Standard messages are uesd for general commands that we send (turn light
    on) to the modem.  We'll send an Msg.OutStandard object, the modem will
    echo that back with an ACK/NAK.  Then we'll get a reply from the device
    as an Msg.InpStandard object which ends the sequence.

    Since many things can be happening at once, the messages are checked to
    see if the device address and command match the command that was sent.
    If they don't, it's not a message this handler should take care of.

    When we get the InptStandard message we expect to see, it will be passed
    to the callback set in the constructor which is usually a method on the
    device to handle the result (or the ACK that the command went through).
    """
    def __init__(self, msg, callback):
        """Constructor

        Args
          msg:      (OutStandard) The output message that was sent.  The
                    reply must match the address and msg.cmd1 field to be
                    processed by this handler.
          callback: Callback function to pass InpStandard messages that match
                    the output to.  Signature: callback(message)
        """
        super().__init__()

        self.addr = msg.to_addr
        self.cmd = msg.cmd1
        self.callback = callback

    #-----------------------------------------------------------------------
    def msg_received(self, protocol, msg):
        """See if we can handle the message.

        See if the message is the expected ACK of our output or the expected
        InpStandard reply message.  If we get a reply, pass it to the
        callback.

        Args:
          protocol:  (Protocol) The Insteon Protocol object
          msg:       Insteon message object that was read.

        Returns:
          Msg.UNKNOWN if we can't handle this message.
          Msg.CONTINUE if we handled the message and expect more.
          Msg.FINISHED if we handled the message and are done.
        """
        # Probably an echo back of our sent message.
        if isinstance(msg, Msg.OutStandard):
            # If the message is the echo back of our message, then continue
            # waiting for a reply.
            if msg.to_addr == self.addr and msg.cmd1 == self.cmd:
                if not msg.is_ack:
                    LOG.error("%s NAK response", self.addr)

                LOG.debug("%s got msg ACK", self.addr)
                return Msg.CONTINUE

            # Message didn't match the expected addr/cmd.
            LOG.debug("%s handler unknown msg", self.addr)
            return Msg.UNKNOWN

        # See if this is the standard message ack/nak we're expecting.
        elif isinstance(msg, Msg.InpStandard):
            # If this message matches our address and command, it's probably
            # the ACK we're expecting.
            if msg.from_addr == self.addr and msg.cmd1 == self.cmd:
                # Run the callback - it's up to the callback to check if this
                # is really the ACK or not.
                self.callback(msg)

                # Indicate no more messages are expected.
                return Msg.FINISHED
            else:
                LOG.info("Possible unexpected message from %s cmd %#04x but "
                         "expected %s cmd %#04x", msg.from_addr, msg.cmd1,
                         self.addr, self.cmd)

        return Msg.UNKNOWN

    #-----------------------------------------------------------------------
